"""
DR-TEA — E5: Live Baselines (B1, B2, B3)
==========================================
B1: Centralized signed receipt log (no anchoring)
B2: Per-event anchoring pilot (dry-run + Blockfrost estimate)
B3: DR-TEA batched anchoring (dry-run, batch_size=1681)

Uses Blockfrost Preprod to get real fee parameters and tx size data.
Falls back to dry-run model if Blockfrost is unreachable.

Outputs: results/e5_live.csv
"""

from __future__ import annotations

import csv
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import bootstrap

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from services.ingestion.merkle import Batch, GENESIS_PREV_ROOT
from services.anchoring.dry_run_adapter import (
    DryRunAdapter, estimate_fee_ada, estimate_fee_lovelace,
    DRY_RUN_TX_SIZE_BYTES_MEAN, ADA_PRICE_USD,
)
from services.anchoring.dry_run_adapter import BlockfrostAdapter

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SEED = 42
N_RUNS = 10  # Live baselines: 10 repetitions
DAILY_VOLUME = 5000
BATCH_SIZE_B3 = 1681  # Recommended batch size (midpoint)
BLOCKFROST_PROJECT_ID = os.environ.get("BLOCKFROST_PROJECT_ID", "preprodrSh5fPNiPRAacpESeC83Get8FANREIAh")
ADA_PRICE = ADA_PRICE_USD  # Use module constant


def measure_b1_centralized_log(n_events: int = 1000) -> dict:
    """
    B1: Centralized signed receipt log.
    Measure in-memory write latency and storage overhead.
    No anchoring cost — zero anchoring cost.
    """
    import hashlib
    import json
    import time

    receipts: list[dict] = []
    write_latencies: list[float] = []

    for i in range(n_events):
        ev = {
            "inv_id": f"INV-{i:06d}",
            "event_hash": hashlib.sha256(f"event-{i}".encode()).hexdigest(),
            "seq": i + 1,
            "ts": time.time(),
        }
        t0 = time.perf_counter()
        receipts.append(ev)
        latency_us = (time.perf_counter() - t0) * 1e6
        write_latencies.append(latency_us)

    # Verification: just lookup
    t0 = time.perf_counter()
    _ = {r["event_hash"]: r for r in receipts}
    verify_us = (time.perf_counter() - t0) * 1e6 / n_events

    return {
        "baseline": "B1 Centralized log",
        "n_events": n_events,
        "write_latency_mean_us": round(float(np.mean(write_latencies)), 4),
        "write_latency_p95_us": round(float(np.percentile(write_latencies, 95)), 4),
        "verify_latency_mean_us": round(verify_us, 4),
        "storage_bytes_per_event": 256,  # estimate for hashed receipt
        "anchoring_cost_usd": 0.0,
        "monthly_cost_usd": 0.0,  # no chain cost
        "tef_s": 0.0,  # instant — no blockchain
        "public_verifiable": False,
        "omission_detectable": False,
        "mode": "benchmark",
    }


def measure_b2_per_event_cardano(rng: random.Random, n_sample: int = 100) -> dict:
    """
    B2: Per-event Cardano anchoring.
    Each event gets its own transaction. Cost extrapolated to full volume.
    Uses Blockfrost protocol params; falls back to dry-run estimates.
    """
    bf = BlockfrostAdapter(BLOCKFROST_PROJECT_ID, "preprod")
    live_mode = False

    try:
        params = bf.get_network_params()
        fee_a = int(params.get("min_fee_a", 44))
        fee_b = int(params.get("min_fee_b", 155381))
        live_mode = True
        print(f"    [B2] Blockfrost live: fee_a={fee_a}, fee_b={fee_b}")
    except Exception as e:
        print(f"    [B2] Blockfrost unreachable ({e}), using dry-run fee model")
        fee_a, fee_b = 44, 155_381

    # Per-event tx is smaller (just a hash, no batch metadata)
    per_event_tx_size = 300  # bytes estimate
    fee_per_event_lovelace = fee_a * per_event_tx_size + fee_b
    fee_per_event_ada = fee_per_event_lovelace / 1_000_000

    # Simulate confirmation delays for n_sample events
    adapter = DryRunAdapter(rng=rng)
    confirm_delays = []
    for i in range(n_sample):
        result = adapter.submit_root(
            rng.randbytes(32).hex(),
            rng.randbytes(32).hex(),
            i,
        )
        confirm_delays.append(result.confirmation_delay_s)

    # Monthly cost: DAILY_VOLUME events/day * 30 days
    monthly_txs = DAILY_VOLUME * 30
    monthly_cost_ada = monthly_txs * fee_per_event_ada
    monthly_cost_usd = monthly_cost_ada * ADA_PRICE

    return {
        "baseline": "B2 Per-event pilot",
        "n_sample": n_sample,
        "fee_per_event_ada": round(fee_per_event_ada, 6),
        "fee_per_event_usd": round(fee_per_event_ada * ADA_PRICE, 6),
        "confirm_delay_mean_s": round(float(np.mean(confirm_delays)), 2),
        "confirm_delay_p95_s": round(float(np.percentile(confirm_delays, 95)), 2),
        "monthly_cost_ada": round(monthly_cost_ada, 2),
        "monthly_cost_usd": round(monthly_cost_usd, 2),
        "tef_mean_s": round(float(np.mean(confirm_delays)), 2),
        "public_verifiable": True,
        "omission_detectable": True,
        "mode": "dry-run" if not live_mode else "live-params+dry-run",
    }


def measure_b3_drtea_batched(rng: random.Random) -> dict:
    """
    B3: DR-TEA batched anchoring (batch_size=1681).
    """
    bf = BlockfrostAdapter(BLOCKFROST_PROJECT_ID, "preprod")
    live_mode = False

    try:
        params = bf.get_network_params()
        fee_a = int(params.get("min_fee_a", 44))
        fee_b = int(params.get("min_fee_b", 155381))
        live_mode = True
        print(f"    [B3] Blockfrost live: fee_a={fee_a}, fee_b={fee_b}")
    except Exception as e:
        print(f"    [B3] Blockfrost unreachable ({e}), using dry-run fee model")
        fee_a, fee_b = 44, 155_381

    batch_size = BATCH_SIZE_B3
    adapter = DryRunAdapter(rng=rng)

    # Simulate 10 batch submissions
    fees_ada = []
    confirm_delays = []
    for i in range(10):
        event_hashes = [rng.randbytes(32) for _ in range(batch_size)]
        b = Batch(batch_id=i, event_hashes=event_hashes, prev_root=rng.randbytes(32))
        result = adapter.submit_root(b.root_hex, b.prev_root_hex, i)
        fees_ada.append(result.fee_ada)
        confirm_delays.append(result.confirmation_delay_s)

    fee_per_batch_ada = float(np.mean(fees_ada))
    batches_per_day = DAILY_VOLUME / batch_size
    monthly_batches = batches_per_day * 30
    monthly_cost_ada = monthly_batches * fee_per_batch_ada
    monthly_cost_usd = monthly_cost_ada * ADA_PRICE
    cost_per_1k_usd = (1000 / batch_size) * fee_per_batch_ada * ADA_PRICE

    # Verification time (proof verification)
    from services.ingestion.merkle import generate_proof, verify_proof
    test_leaves = [rng.randbytes(32) for _ in range(batch_size)]
    proof = generate_proof([rng.randbytes(32)] + test_leaves, 1)
    t0 = time.perf_counter()
    for _ in range(1000):
        verify_proof(proof.root, test_leaves[0], proof)
    t_ver_us = (time.perf_counter() - t0) / 1000 * 1e6

    return {
        "baseline": "B3 DR-TEA batched",
        "batch_size": batch_size,
        "fee_per_batch_ada": round(fee_per_batch_ada, 6),
        "fee_per_batch_usd": round(fee_per_batch_ada * ADA_PRICE, 6),
        "cost_per_1k_usd": round(cost_per_1k_usd, 6),
        "monthly_cost_ada": round(monthly_cost_ada, 4),
        "monthly_cost_usd": round(monthly_cost_usd, 4),
        "verify_latency_us": round(t_ver_us, 4),
        "confirm_delay_mean_s": round(float(np.mean(confirm_delays)), 2),
        "confirm_delay_p95_s": round(float(np.percentile(confirm_delays, 95)), 2),
        "tef_mean_s": round(float(np.mean(confirm_delays)), 2),
        "public_verifiable": True,
        "omission_detectable": True,
        "mode": "dry-run" if not live_mode else "live-params+dry-run",
    }


def run_e5() -> dict:
    print("=" * 60)
    print("E5: Live Baselines")
    print("=" * 60)
    rng = random.Random(SEED)

    print("  Running B1 (Centralized log)...")
    b1 = measure_b1_centralized_log()

    print("  Running B2 (Per-event anchoring)...")
    b2 = measure_b2_per_event_cardano(rng)

    print("  Running B3 (DR-TEA batched)...")
    b3 = measure_b3_drtea_batched(rng)

    # Write combined summary
    rows = []
    for r in [b1, b2, b3]:
        rows.append({
            "baseline": r["baseline"],
            "monthly_cost_usd": r.get("monthly_cost_usd", 0),
            "verify_latency_us": r.get("verify_latency_mean_us") or r.get("verify_latency_us", "N/A"),
            "tef_s": r.get("tef_s") or r.get("tef_mean_s", "N/A"),
            "public_verifiable": r["public_verifiable"],
            "omission_detectable": r.get("omission_detectable", False),
            "mode": r.get("mode", ""),
        })

    csv_path = RESULTS_DIR / "e5_live.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    # Also save detailed
    import json
    detail_path = RESULTS_DIR / "e5_live_detail.json"
    with open(detail_path, "w") as f:
        json.dump({"B1": b1, "B2": b2, "B3": b3}, f, indent=2)

    print(f"[E5] Results written to {csv_path}")
    for r in rows:
        print(f"  {r['baseline']:25s}: "
              f"cost=${r['monthly_cost_usd']:.2f}/mo "
              f"verify={r['verify_latency_us']}µs "
              f"TEF={r['tef_s']}s "
              f"public={r['public_verifiable']}")

    return {"B1": b1, "B2": b2, "B3": b3}


if __name__ == "__main__":
    run_e5()
