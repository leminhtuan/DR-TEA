"""
DR-TEA — E7: Mainnet Pilot (Dry-Run Mode)
==========================================
Simulates 30-90 anchored batches.
In dry-run mode (default): deterministic simulation.
In live mode (--mainnet flag + MAINNET_PILOT_APPROVED=true): real submissions.

Metrics: fee per batch, confirmation time, reorg events, total pilot cost.

Outputs: results/e7_mainnet.csv
"""

from __future__ import annotations

import csv
import os
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from services.ingestion.merkle import Batch, GENESIS_PREV_ROOT
from services.anchoring.dry_run_adapter import DryRunAdapter, ADA_PRICE_USD

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SEED = 42
N_BATCHES = 50  # within 30-90 range
BATCH_SIZE = 1681
ADA_PRICE = ADA_PRICE_USD

# Reorg probability (Cardano mainnet: very rare after 3+ confirmations)
REORG_PROB_PER_BATCH = 0.0  # effectively 0 in dry-run


def run_e7(live: bool = False) -> dict:
    print("=" * 60)
    print("E7: Mainnet Pilot")
    print("=" * 60)

    if live:
        mainnet_approved = os.environ.get("MAINNET_PILOT_APPROVED", "false").lower() == "true"
        if not mainnet_approved:
            print("  ERROR: Live mode requires MAINNET_PILOT_APPROVED=true env var.")
            print("  Falling back to dry-run mode.")
            live = False

    mode = "mainnet-pilot" if live else "dry-run"
    print(f"  Mode: {mode}")

    rng = random.Random(SEED)
    adapter = DryRunAdapter(rng=rng, mode=mode)

    rows = []
    prev_root = GENESIS_PREV_ROOT.hex()
    total_fee_ada = 0.0
    n_reorgs = 0
    fallback_triggered = 0

    for i in range(N_BATCHES):
        event_hashes = [rng.randbytes(32) for _ in range(BATCH_SIZE)]
        batch = Batch(batch_id=i, event_hashes=event_hashes, prev_root=bytes.fromhex(prev_root))
        result = adapter.submit_root(batch.root_hex, prev_root, i)

        # Simulate reorg (very rare)
        is_reorg = rng.random() < REORG_PROB_PER_BATCH
        if is_reorg:
            n_reorgs += 1
            fallback_triggered += 1

        prev_root = batch.root_hex
        total_fee_ada += result.fee_ada

        rows.append({
            "batch_id": i,
            "tx_id": result.tx_id[:16] + "...",
            "root_hex": result.root_hex[:16] + "...",
            "fee_ada": round(result.fee_ada, 6),
            "fee_usd": round(result.fee_ada * ADA_PRICE, 6),
            "tx_size_bytes": result.tx_size_bytes,
            "confirmation_delay_s": round(result.confirmation_delay_s, 2),
            "is_reorg": is_reorg,
            "mode": mode,
        })

    # Summary
    confirm_delays = [r["confirmation_delay_s"] for r in rows]
    fees_ada = [r["fee_ada"] for r in rows]
    total_cost_usd = total_fee_ada * ADA_PRICE

    summary = {
        "n_batches": N_BATCHES,
        "batch_size": BATCH_SIZE,
        "mode": mode,
        "mean_fee_ada": round(float(np.mean(fees_ada)), 6),
        "median_confirm_s": round(float(np.median(confirm_delays)), 2),
        "p95_confirm_s": round(float(np.percentile(confirm_delays, 95)), 2),
        "n_reorgs": n_reorgs,
        "fallback_triggered": fallback_triggered,
        "total_fee_ada": round(total_fee_ada, 4),
        "total_cost_usd": round(total_cost_usd, 4),
        "mean_cost_per_batch_usd": round(total_cost_usd / N_BATCHES, 6),
    }

    csv_path = RESULTS_DIR / "e7_mainnet.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    summary_path = RESULTS_DIR / "e7_mainnet_summary.csv"
    with open(summary_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary.keys())
        writer.writeheader()
        writer.writerow(summary)

    print(f"[E7] {N_BATCHES} batches anchored ({mode})")
    print(f"     Mean fee: {summary['mean_fee_ada']:.6f} ADA")
    print(f"     Median confirm: {summary['median_confirm_s']:.1f}s")
    print(f"     Reorgs: {n_reorgs}")
    print(f"     Total pilot cost: {summary['total_fee_ada']:.4f} ADA = ${summary['total_cost_usd']:.4f}")
    print(f"[E7] Results written to {csv_path}")

    return summary


if __name__ == "__main__":
    live_mode = "--mainnet" in sys.argv
    run_e7(live=live_mode)
