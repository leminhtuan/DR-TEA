"""
DR-TEA — E4: SLA-Window Sensitivity
======================================
Delta values: 60, 300, 600, 1800, 3600 seconds
Metrics: ODR, FPR, MTTD (Mean Time To Detect)
Fixed omission rate: 5%, 30 runs.

Outputs: results/e4_sla.csv
         figures/fig4_sla_sensitivity.pdf (via analyze.py)
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

import numpy as np
from scipy.stats import bootstrap

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from services.monitor.monitor import (
    OmissionMonitor, AnchorRecord, FaultInjector,
    compute_omission_metrics, Dispute,
)
from services.receipts.receipt_service import DualReceiptIssuer, Receipt
from services.ingestion.merkle import Batch, GENESIS_PREV_ROOT
from services.anchoring.dry_run_adapter import DryRunAdapter

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SEED = 42
N_RUNS = 30
N_EVENTS = 1000
OMISSION_RATE = 0.05
BATCH_SIZE = 500
SLA_WINDOWS = [60, 300, 600, 1800, 3600]

import random as _rand
_rng_keys = _rand.Random(SEED)
SSC_PRIV_KEY_HEX = _rng_keys.randbytes(32).hex()
SCHOOL_PRIV_KEY_HEX = _rng_keys.randbytes(32).hex()


def simulate_run(sla_window_s: float, run_id: int, rng: random.Random) -> dict:
    base_ts = float(run_id * N_EVENTS * 0.2)

    # Generate events + receipts
    event_hashes = [rng.randbytes(32).hex() for _ in range(N_EVENTS)]
    all_hashes_set = set(event_hashes)

    issuer = DualReceiptIssuer(SSC_PRIV_KEY_HEX, SCHOOL_PRIV_KEY_HEX)
    receipts: list[Receipt] = []
    for i, h in enumerate(event_hashes):
        ssc_r, _ = issuer.issue(h, f"INV-{run_id}-{i:05d}", school_available=True)
        ssc_r.ts_issued = base_ts + i * 0.1
        receipts.append(ssc_r)

    # Fault injection
    fi = FaultInjector(rng)
    included, omitted = fi.inject_omissions(event_hashes, OMISSION_RATE)
    omitted_set = set(event_hashes) - set(included)

    # Anchor non-omitted events
    anchor_records: list[AnchorRecord] = []
    adapter = DryRunAdapter(rng=rng)
    prev_root = GENESIS_PREV_ROOT

    batch_hashes = [bytes.fromhex(h) for h in included]
    for start in range(0, len(batch_hashes), BATCH_SIZE):
        chunk = batch_hashes[start:start + BATCH_SIZE]
        if not chunk:
            continue
        b = Batch(batch_id=start // BATCH_SIZE, event_hashes=chunk, prev_root=prev_root)
        prev_root = b.root
        anchor = adapter.submit_root(b.root_hex, b.prev_root_hex, b.batch_id)
        ar = AnchorRecord(
            batch_id=b.batch_id,
            tx_id=anchor.tx_id,
            root_hex=b.root_hex,
            confirmed_at=base_ts + anchor.confirmation_delay_s,
            event_hash_hexes=included[start:start + BATCH_SIZE],
        )
        anchor_records.append(ar)

    # Monitor check
    monitor = OmissionMonitor("MON-SLA", sla_window_s=sla_window_s)
    check_time = base_ts + N_EVENTS * 0.1 + sla_window_s + 10.0
    disputes = monitor.run_check(receipts, anchor_records, current_time=check_time)
    disputed_set = {d.event_hash_hex for d in disputes}

    # Metrics
    metrics = compute_omission_metrics(omitted_set, disputed_set, all_hashes_set)

    # MTTD
    mttd_values = [d.mttd for d in disputes if d.event_hash_hex in omitted_set]
    mttd_mean = float(np.mean(mttd_values)) if mttd_values else 0.0

    return {
        "sla_window_s": sla_window_s,
        "run_id": run_id,
        "odr": metrics.odr,
        "fpr": metrics.fpr,
        "precision": metrics.precision,
        "mttd_s": mttd_mean,
    }


def run_e4() -> list[dict]:
    print("=" * 60)
    print("E4: SLA-Window Sensitivity")
    print("=" * 60)

    rng = random.Random(SEED)
    raw: list[dict] = []

    for sla in SLA_WINDOWS:
        print(f"  Δ={sla}s: ", end="", flush=True)
        for run in range(N_RUNS):
            row = simulate_run(float(sla), run, rng)
            raw.append(row)
        print(f"{N_RUNS} runs")

    summary = []
    for sla in SLA_WINDOWS:
        subset = [r for r in raw if r["sla_window_s"] == sla]
        odr_arr = np.array([r["odr"] for r in subset])
        fpr_arr = np.array([r["fpr"] for r in subset])
        mttd_arr = np.array([r["mttd_s"] for r in subset])

        def ci95(arr: np.ndarray) -> tuple[float, float]:
            if arr.std() < 1e-10:
                return float(arr[0]), float(arr[0])
            res = bootstrap((arr,), np.mean, n_resamples=1000,
                            confidence_level=0.95, random_state=SEED, method="percentile")
            return float(res.confidence_interval.low), float(res.confidence_interval.high)

        odr_lo, odr_hi = ci95(odr_arr)
        fpr_lo, fpr_hi = ci95(fpr_arr)

        summary.append({
            "sla_window_s": sla,
            "odr_mean": round(float(np.mean(odr_arr)), 4),
            "odr_ci_lo": round(odr_lo, 4),
            "odr_ci_hi": round(odr_hi, 4),
            "fpr_mean": round(float(np.mean(fpr_arr)), 4),
            "fpr_ci_lo": round(fpr_lo, 4),
            "fpr_ci_hi": round(fpr_hi, 4),
            "mttd_mean_s": round(float(np.mean(mttd_arr)), 2),
        })

    # Also save raw for figure generation
    raw_path = RESULTS_DIR / "e4_sla_raw.csv"
    with open(raw_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=raw[0].keys())
        writer.writeheader()
        writer.writerows(raw)

    csv_path = RESULTS_DIR / "e4_sla.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary[0].keys())
        writer.writeheader()
        writer.writerows(summary)

    print(f"[E4] Results written to {csv_path}")
    for row in summary:
        print(f"  Δ={row['sla_window_s']:5d}s: ODR={row['odr_mean']:.4f} "
              f"[{row['odr_ci_lo']:.4f},{row['odr_ci_hi']:.4f}] "
              f"FPR={row['fpr_mean']:.4f} MTTD={row['mttd_mean_s']:.1f}s")
    return summary


if __name__ == "__main__":
    run_e4()
