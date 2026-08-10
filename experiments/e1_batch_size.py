"""
DR-TEA — E1: Batch-Size Trade-off
===================================
Batch sizes: 100, 500, 1000, 1681, 2000, 5000
30 simulation runs each.
Metrics: L_sub, T_ver (µs), S_π (bytes), C_1k (USD), TEF (s)

Outputs: results/e1_batch_size.csv
"""

from __future__ import annotations

import csv
import random
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import bootstrap

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from services.ingestion.merkle import Batch, GENESIS_PREV_ROOT, verify_proof
from services.anchoring.dry_run_adapter import DryRunAdapter, estimate_fee_ada, DRY_RUN_TX_SIZE_BYTES_MEAN

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SEED = 42
N_RUNS = 30
BATCH_SIZES = [100, 500, 1000, 1681, 2000, 5000]

# ADA price for cost calculation (use P50 from E8 — will be updated; use ~$0.44 as initial)
ADA_PRICE_USD = 0.44

# Daily event volume (representative SSC workload)
DAILY_VOLUME = 5000


def run_single(batch_size: int, run_id: int, rng: random.Random) -> dict:
    """Run a single batch-size experiment."""

    # Generate event hashes (32-byte random values simulating canonical hashes)
    event_hashes = [rng.randbytes(32) for _ in range(batch_size)]

    # Build batch (Eq. 6)
    prev_root = rng.randbytes(32)
    t0 = time.perf_counter()
    batch = Batch(batch_id=run_id, event_hashes=event_hashes, prev_root=prev_root)
    t_batch_build = (time.perf_counter() - t0) * 1e6  # µs

    # Simulated anchoring (dry-run)
    adapter = DryRunAdapter(rng=rng)
    anchor_result = adapter.submit_root(
        root_hex=batch.root_hex,
        prev_root_hex=batch.prev_root_hex,
        batch_id=run_id,
    )

    # L_sub: submission latency = confirmation delay (simulated)
    l_sub = anchor_result.confirmation_delay_s

    # T_ver: measure time to verify one proof (Eq. 7)
    proof_idx = rng.randint(0, batch_size - 1)
    proof = batch.get_event_proof(proof_idx)
    t_ver_start = time.perf_counter()
    for _ in range(100):  # repeat 100x for stable timing
        result = verify_proof(batch.root_hex, event_hashes[proof_idx], proof)
    t_ver = (time.perf_counter() - t_ver_start) / 100 * 1e6  # µs
    assert result, "Proof verification failed in E1"

    # S_π: proof size in bytes
    s_pi = proof.size_bytes()

    # C_1k: cost per 1000 events
    # batches_per_1k = 1000 / batch_size
    # cost_per_batch_usd = fee_ada * ADA_PRICE_USD
    fee_ada = estimate_fee_ada(int(DRY_RUN_TX_SIZE_BYTES_MEAN))
    batches_per_1k = 1000.0 / batch_size
    c_1k = batches_per_1k * fee_ada * ADA_PRICE_USD

    # TEF: Time-to-Evidence-Finality = batch_build_time + L_sub + (batch accumulation time)
    # Batch accumulation: at 5000 events/day, accumulation time = batch_size / (5000/86400) seconds
    t_accumulate = batch_size / (DAILY_VOLUME / 86400.0)
    tef = t_accumulate + anchor_result.confirmation_delay_s  # seconds

    return {
        "batch_size": batch_size,
        "run_id": run_id,
        "l_sub_s": round(l_sub, 3),
        "t_ver_us": round(t_ver, 4),
        "s_pi_bytes": s_pi,
        "c_1k_usd": round(c_1k, 6),
        "tef_s": round(tef, 2),
        "fee_ada": round(fee_ada, 6),
        "tx_size_bytes": anchor_result.tx_size_bytes,
    }


def summarize(rows: list[dict], batch_size: int) -> dict:
    """Compute mean ± 95% CI for a batch size."""
    subset = [r for r in rows if r["batch_size"] == batch_size]

    def ci(values: list[float]) -> tuple[float, float, float]:
        arr = np.array(values)
        mean = float(np.mean(arr))
        res = bootstrap(
            (arr,), np.mean,
            n_resamples=1000, confidence_level=0.95, random_state=SEED, method="percentile"
        )
        lo, hi = res.confidence_interval
        return mean, float(lo), float(hi)

    l_sub_mean, l_sub_lo, l_sub_hi = ci([r["l_sub_s"] for r in subset])
    t_ver_mean, t_ver_lo, t_ver_hi = ci([r["t_ver_us"] for r in subset])
    s_pi_vals = [r["s_pi_bytes"] for r in subset]
    c_1k_mean, c_1k_lo, c_1k_hi = ci([r["c_1k_usd"] for r in subset])
    tef_mean, tef_lo, tef_hi = ci([r["tef_s"] for r in subset])

    return {
        "batch_size": batch_size,
        "n_runs": len(subset),
        "l_sub_mean_s": round(l_sub_mean, 3),
        "l_sub_ci_lo_s": round(l_sub_lo, 3),
        "l_sub_ci_hi_s": round(l_sub_hi, 3),
        "t_ver_mean_us": round(t_ver_mean, 4),
        "t_ver_ci_lo_us": round(t_ver_lo, 4),
        "t_ver_ci_hi_us": round(t_ver_hi, 4),
        "s_pi_bytes": int(np.mean(s_pi_vals)),
        "c_1k_mean_usd": round(c_1k_mean, 6),
        "c_1k_ci_lo_usd": round(c_1k_lo, 6),
        "c_1k_ci_hi_usd": round(c_1k_hi, 6),
        "tef_mean_s": round(tef_mean, 2),
        "tef_ci_lo_s": round(tef_lo, 2),
        "tef_ci_hi_s": round(tef_hi, 2),
    }


def run_e1() -> list[dict]:
    print("=" * 60)
    print("E1: Batch-Size Trade-off")
    print("=" * 60)
    rng = random.Random(SEED)
    raw_rows: list[dict] = []

    for bs in BATCH_SIZES:
        print(f"  batch_size={bs}: ", end="", flush=True)
        for run in range(N_RUNS):
            row = run_single(bs, run, rng)
            raw_rows.append(row)
        print(f"{N_RUNS} runs done")

    # Write raw
    raw_path = RESULTS_DIR / "e1_batch_size_raw.csv"
    if raw_rows:
        with open(raw_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=raw_rows[0].keys())
            writer.writeheader()
            writer.writerows(raw_rows)

    # Summarize
    summary = [summarize(raw_rows, bs) for bs in BATCH_SIZES]

    csv_path = RESULTS_DIR / "e1_batch_size.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary[0].keys())
        writer.writeheader()
        writer.writerows(summary)

    print(f"[E1] Results written to {csv_path}")
    for row in summary:
        print(f"  m={row['batch_size']:5d}: L_sub={row['l_sub_mean_s']:.1f}s "
              f"T_ver={row['t_ver_mean_us']:.4f}µs "
              f"S_π={row['s_pi_bytes']}B "
              f"C_1k=${row['c_1k_mean_usd']:.5f} "
              f"TEF={row['tef_mean_s']:.0f}s")
    return summary


if __name__ == "__main__":
    run_e1()
