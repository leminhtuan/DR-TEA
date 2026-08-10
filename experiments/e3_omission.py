"""
DR-TEA — E3: Omission Detection and False Positives
=====================================================
Configurations:
  - no_receipts: 5% omission rate
  - receipts_only: 5% omission rate
  - receipts_monitor (1%, 5%, 10% omission rates)

Co-sign availability: 0.7, 0.9, 1.0
Monitor liveness: 0.95, 1.0
SLA window: 300s (default)

Outputs: results/e3_omission.csv, results/e3_confusion.csv
"""

from __future__ import annotations

import csv
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.stats import bootstrap, kruskal

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from services.monitor.monitor import (
    OmissionMonitor, AnchorRecord, FaultInjector,
    compute_omission_metrics, OmissionMetrics,
)
from services.receipts.receipt_service import DualReceiptIssuer, Receipt
from services.ingestion.merkle import Batch, GENESIS_PREV_ROOT
from services.anchoring.dry_run_adapter import DryRunAdapter

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SEED = 42
N_RUNS = 30
N_EVENTS = 1000
SLA_WINDOW = 300.0  # seconds (simulated)
BATCH_SIZE = 500
ADA_PRICE_USD = 0.44

# Generate Ed25519 keys deterministically for testing
import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
_rng_keys = random.Random(SEED)
SSC_PRIV_KEY_HEX = _rng_keys.randbytes(32).hex()
SCHOOL_PRIV_KEY_HEX = _rng_keys.randbytes(32).hex()


@dataclass
class ExperimentConfig:
    name: str
    omission_rate: float
    use_receipts: bool
    use_monitor: bool
    cosign_prob: float = 1.0
    monitor_liveness: float = 1.0


CONFIGS = [
    ExperimentConfig("No receipts", 0.05, False, False),
    ExperimentConfig("Receipts only", 0.05, True, False),
    ExperimentConfig("Receipts + monitor", 0.01, True, True),
    ExperimentConfig("Receipts + monitor", 0.05, True, True),
    ExperimentConfig("Receipts + monitor", 0.10, True, True),
]


def simulate_one_run(cfg: ExperimentConfig, run_id: int, rng: random.Random) -> OmissionMetrics:
    """
    Simulate one run of the omission detection experiment.

    Strategy:
    - Generate N_EVENTS event hashes.
    - Issue SSC receipts for all events.
    - Fault injector selectively omits a fraction from batching.
    - Anchor only non-omitted events in batches.
    - Monitor checks for unanchored receipts past SLA window.
    - Compute TP/FP/FN/TN.
    """
    # Step 1: Generate event hashes
    event_hashes = [rng.randbytes(32).hex() for _ in range(N_EVENTS)]
    all_hashes_set = set(event_hashes)

    # Step 2: Issue receipts (simulated)
    if cfg.use_receipts:
        issuer = DualReceiptIssuer(SSC_PRIV_KEY_HEX, SCHOOL_PRIV_KEY_HEX)
        receipts: list[Receipt] = []
        base_ts = 1_000_000.0  # simulated epoch
        for i, h in enumerate(event_hashes):
            school_ok = rng.random() < cfg.cosign_prob
            ssc_r, _ = issuer.issue(h, f"INV-{i:06d}", school_available=school_ok)
            ssc_r.ts_issued = base_ts + i * 0.1  # spread receipts in time
            receipts.append(ssc_r)
    else:
        receipts = []

    # Step 3: Fault injection (omit a fraction from batching)
    fi = FaultInjector(rng)
    included, omitted = fi.inject_omissions(event_hashes, cfg.omission_rate)
    included_set = set(included)
    omitted_set = set(event_hashes) - included_set

    # Step 4: Anchor non-omitted events in batches
    anchor_records: list[AnchorRecord] = []
    adapter = DryRunAdapter(rng=rng)

    batch_event_hashes = [bytes.fromhex(h) for h in included]
    prev_root = GENESIS_PREV_ROOT

    for start in range(0, len(batch_event_hashes), BATCH_SIZE):
        chunk = batch_event_hashes[start:start + BATCH_SIZE]
        if not chunk:
            continue
        batch = Batch(batch_id=start // BATCH_SIZE, event_hashes=chunk, prev_root=prev_root)
        prev_root = batch.root
        anchor = adapter.submit_root(
            root_hex=batch.root_hex,
            prev_root_hex=batch.prev_root_hex,
            batch_id=start // BATCH_SIZE,
        )
        ar = AnchorRecord(
            batch_id=batch.batch_id,
            tx_id=anchor.tx_id,
            root_hex=batch.root_hex,
            confirmed_at=base_ts + anchor.confirmation_delay_s if cfg.use_receipts else 0.0,
            event_hash_hexes=list(included[start:start + BATCH_SIZE]),
        )
        anchor_records.append(ar)

    # Step 5: Monitor check
    if cfg.use_monitor and receipts:
        monitor = OmissionMonitor("MON-01", sla_window_s=SLA_WINDOW)
        # Simulate time after SLA window has elapsed
        check_time = base_ts + N_EVENTS * 0.1 + SLA_WINDOW + 10.0

        # Apply monitor liveness: with prob (1 - liveness), monitor is down
        if rng.random() < cfg.monitor_liveness:
            disputes = monitor.run_check(receipts, anchor_records, current_time=check_time)
            disputed_hashes = {d.event_hash_hex for d in disputes}
        else:
            disputed_hashes = set()  # monitor was down
    else:
        disputed_hashes = set()

    # Step 6: Compute metrics
    metrics = compute_omission_metrics(omitted_set, disputed_hashes, all_hashes_set)
    return metrics


def run_e3() -> tuple[list[dict], list[dict]]:
    print("=" * 60)
    print("E3: Omission Detection and False Positives")
    print("=" * 60)

    rng = random.Random(SEED)
    all_rows: list[dict] = []
    confusion_rows: list[dict] = []

    for cfg in CONFIGS:
        print(f"  {cfg.name}, rate={cfg.omission_rate:.0%}: ", end="", flush=True)
        run_metrics: list[OmissionMetrics] = []
        for run in range(N_RUNS):
            m = simulate_one_run(cfg, run, rng)
            run_metrics.append(m)
        print(f"{N_RUNS} runs done")

        odr_vals = np.array([m.odr for m in run_metrics])
        fpr_vals = np.array([m.fpr for m in run_metrics])
        prec_vals = np.array([m.precision for m in run_metrics])
        rec_vals = np.array([m.recall for m in run_metrics])

        def ci95(arr: np.ndarray) -> tuple[float, float]:
            if arr.std() < 1e-10:
                return float(arr[0]), float(arr[0])
            res = bootstrap((arr,), np.mean, n_resamples=1000,
                            confidence_level=0.95, random_state=SEED, method="percentile")
            return float(res.confidence_interval.low), float(res.confidence_interval.high)

        odr_lo, odr_hi = ci95(odr_vals)
        fpr_lo, fpr_hi = ci95(fpr_vals)

        all_rows.append({
            "configuration": cfg.name,
            "omission_rate_pct": f"{cfg.omission_rate * 100:.0f}%",
            "odr_mean": round(float(np.mean(odr_vals)), 4),
            "odr_ci_lo": round(odr_lo, 4),
            "odr_ci_hi": round(odr_hi, 4),
            "fpr_mean": round(float(np.mean(fpr_vals)), 4),
            "fpr_ci_lo": round(fpr_lo, 4),
            "fpr_ci_hi": round(fpr_hi, 4),
            "precision_mean": round(float(np.mean(prec_vals)), 4),
            "recall_mean": round(float(np.mean(rec_vals)), 4),
        })

        # Confusion matrix (aggregate)
        tp = sum(m.tp for m in run_metrics)
        fp = sum(m.fp for m in run_metrics)
        fn = sum(m.fn for m in run_metrics)
        tn = sum(m.tn for m in run_metrics)
        confusion_rows.append({
            "configuration": cfg.name,
            "omission_rate_pct": f"{cfg.omission_rate * 100:.0f}%",
            "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        })

    # Kruskal-Wallis test across configurations (receipts+monitor at different rates)
    rm_rows = [r for r in all_rows if r["configuration"] == "Receipts + monitor"]
    print("\n  Kruskal-Wallis on ODR across omission rates (receipts+monitor):")
    # Cannot run KW without multiple samples; note in output
    print("  [Statistical analysis in analyze.py with per-run data]")

    csv_path = RESULTS_DIR / "e3_omission.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
        writer.writeheader()
        writer.writerows(all_rows)

    conf_path = RESULTS_DIR / "e3_confusion.csv"
    with open(conf_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=confusion_rows[0].keys())
        writer.writeheader()
        writer.writerows(confusion_rows)

    print(f"[E3] Results written to {csv_path}")
    for row in all_rows:
        print(f"  {row['configuration']:25s} rate={row['omission_rate_pct']:4s} "
              f"ODR={row['odr_mean']:.4f} [{row['odr_ci_lo']:.4f},{row['odr_ci_hi']:.4f}] "
              f"FPR={row['fpr_mean']:.4f}")

    return all_rows, confusion_rows


if __name__ == "__main__":
    run_e3()
