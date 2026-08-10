"""
DR-TEA — E9: Domain Transferability
======================================
Runs the W2 secondary-domain workload (50,000 events) through the same
ingestion, batching, and verification pipeline as W1.

Metrics:
  - Schema changes (added fields)
  - Processing runtime overhead vs W1
  - Proof verification time
  - FIR_syn (same pipeline, different schema)

Outputs: results/e9_domain.csv
"""

from __future__ import annotations

import csv
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from services.ingestion.canonicalizer import IngestionGateway
from services.ingestion.merkle import Batch, GENESIS_PREV_ROOT, verify_proof
from benchmark.generator.generate_k12 import generate_k12_workload
from benchmark.generator.generate_secondary_domain import generate_secondary_workload

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SEED = 42
BATCH_SIZE = 1681


def process_workload(
    events: list[dict],
    label: str,
    rng: random.Random,
) -> dict:
    """
    Run events through the ingestion + batching + verification pipeline.
    Returns timing and metric results.
    """
    gw = IngestionGateway()
    n_total = len(events)
    n_accepted = 0
    n_rejected_schema = 0
    n_rejected_dupe = 0
    event_hashes: list[bytes] = []

    t0 = time.perf_counter()
    for ev in events:
        result = gw.ingest(ev)
        if result.accepted:
            n_accepted += 1
            event_hashes.append(bytes.fromhex(result.hash_hex))
        elif result.reason == "DUPLICATE_IDEM_KEY":
            n_rejected_dupe += 1
        else:
            n_rejected_schema += 1
    t_ingest = time.perf_counter() - t0

    # Batch commitment (Eq. 6)
    prev_root = GENESIS_PREV_ROOT
    batches: list[Batch] = []
    t_batch_start = time.perf_counter()
    for start in range(0, len(event_hashes), BATCH_SIZE):
        chunk = event_hashes[start:start + BATCH_SIZE]
        if not chunk:
            continue
        b = Batch(batch_id=len(batches), event_hashes=chunk, prev_root=prev_root)
        prev_root = b.root
        batches.append(b)
    t_batch = time.perf_counter() - t_batch_start

    # Proof verification timing (sample 100 events)
    if batches and event_hashes:
        sample_batch = batches[0]
        sample_size = min(100, sample_batch.size())
        sample_indices = rng.sample(range(sample_batch.size()), sample_size)

        t_ver_start = time.perf_counter()
        for idx in sample_indices:
            proof = sample_batch.get_event_proof(idx)
            verify_proof(sample_batch.root_hex, sample_batch.event_hashes[idx], proof)
        t_ver = (time.perf_counter() - t_ver_start) / sample_size * 1e6  # µs per proof
    else:
        t_ver = 0.0

    fir_syn = (n_rejected_schema) / n_total if n_total > 0 else 0.0

    return {
        "domain": label,
        "n_events": n_total,
        "n_accepted": n_accepted,
        "n_rejected_schema": n_rejected_schema,
        "n_rejected_dupe": n_rejected_dupe,
        "n_batches": len(batches),
        "batch_size": BATCH_SIZE,
        "ingest_time_s": round(t_ingest, 4),
        "batch_time_s": round(t_batch, 4),
        "throughput_eps": round(n_accepted / t_ingest if t_ingest > 0 else 0, 2),
        "verify_time_us": round(t_ver, 4),
        "fir_syn": round(fir_syn, 6),
    }


def run_e9() -> list[dict]:
    print("=" * 60)
    print("E9: Domain Transferability")
    print("=" * 60)

    data_dir = ROOT / "benchmark" / "data"
    rng = random.Random(SEED)

    # Generate W1 (K-12)
    print("  Generating W1 (K-12, 100k events)...")
    w1_events, w1_stats = generate_k12_workload(output_dir=data_dir)

    # Generate W2 (Secondary domain)
    print("  Generating W2 (Secondary, 50k events)...")
    w2_events, w2_stats = generate_secondary_workload(output_dir=data_dir)

    # Process W1
    print(f"  Processing W1 ({len(w1_events)} events)...")
    r_w1 = process_workload(w1_events, "K-12", rng)

    # Process W2
    print(f"  Processing W2 ({len(w2_events)} events)...")
    r_w2 = process_workload(w2_events, "University/Utility", rng)

    # Compute overhead ratio
    overhead_ratio = (r_w2["throughput_eps"] / r_w1["throughput_eps"]
                      if r_w1["throughput_eps"] > 0 else 1.0)

    # Schema change analysis
    schema_changes_w1 = 0  # baseline
    schema_changes_w2 = len(w2_stats["schema_changes"]["added_fields"])

    rows = []
    for r in [r_w1, r_w2]:
        rows.append(r)

    # Add comparison row
    comparison = {
        "domain": "COMPARISON",
        "schema_changes_vs_baseline": schema_changes_w2,
        "throughput_ratio_w2_vs_w1": round(overhead_ratio, 4),
        "verify_overhead_us": round(r_w2["verify_time_us"] - r_w1["verify_time_us"], 4),
        "core_pipeline_unchanged": True,
    }

    csv_path = RESULTS_DIR / "e9_domain.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    import json
    comp_path = RESULTS_DIR / "e9_comparison.json"
    with open(comp_path, "w") as f:
        json.dump({
            "W1": r_w1,
            "W2": r_w2,
            "comparison": comparison,
            "w2_schema_changes": w2_stats["schema_changes"],
        }, f, indent=2)

    print(f"[E9] Results written to {csv_path}")
    print(f"  W1 K-12:               {r_w1['n_accepted']:6d} accepted / {r_w1['n_events']} total "
          f"throughput={r_w1['throughput_eps']:.0f} ev/s  verify={r_w1['verify_time_us']:.4f}µs")
    print(f"  W2 Secondary:          {r_w2['n_accepted']:6d} accepted / {r_w2['n_events']} total "
          f"throughput={r_w2['throughput_eps']:.0f} ev/s  verify={r_w2['verify_time_us']:.4f}µs")
    print(f"  Schema changes added:  {schema_changes_w2} fields")
    print(f"  Throughput ratio:      {overhead_ratio:.4f}")

    return rows


if __name__ == "__main__":
    run_e9()
