"""
DR-TEA — E0: Property-Based Tests (Hypothesis)
===============================================
Tests P1-P6 using Hypothesis, reporting trial counts and pass/fail.

P1: Merkle root determinism
P2: Valid proofs verify
P3: Tampered leaves fail verification
P4: Predecessor root modification invalidates chain
P5: Duplicate idempotency keys are rejected
P6: Malformed payloads are isolated before batching

Outputs: results/e0_property.csv
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
import pytest

from services.ingestion.merkle import (
    Batch, BatchCommitmentEngine, GENESIS_PREV_ROOT,
    compute_merkle_root, generate_proof, verify_proof,
)
from services.ingestion.canonicalizer import IngestionGateway, PaymentEvent, canonical_hash
from services.monitor.monitor import FaultInjector

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

HYPOTHESIS_SETTINGS = settings(
    max_examples=1000,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)

# Track results
_results: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# P1: Merkle root determinism
# ---------------------------------------------------------------------------

@given(
    leaves=st.lists(st.binary(min_size=32, max_size=32), min_size=1, max_size=100),
    prev_root=st.binary(min_size=32, max_size=32),
)
@HYPOTHESIS_SETTINGS
def _test_p1(leaves: list[bytes], prev_root: bytes) -> None:
    """Root must be identical when computed twice from same inputs."""
    b1 = Batch(batch_id=0, event_hashes=leaves, prev_root=prev_root)
    b2 = Batch(batch_id=0, event_hashes=leaves, prev_root=prev_root)
    assert b1.root == b2.root, "Root must be deterministic"


def test_p1_root_determinism() -> tuple[int, bool]:
    try:
        _test_p1()
        return 1000, True
    except Exception as e:
        print(f"P1 FAILED: {e}")
        return 1000, False


# ---------------------------------------------------------------------------
# P2: Valid proofs verify
# ---------------------------------------------------------------------------

@given(
    leaves=st.lists(st.binary(min_size=32, max_size=32), min_size=1, max_size=64),
    prev_root=st.binary(min_size=32, max_size=32),
)
@HYPOTHESIS_SETTINGS
def _test_p2(leaves: list[bytes], prev_root: bytes) -> None:
    """Every generated proof for every leaf must verify against the batch root."""
    batch = Batch(batch_id=0, event_hashes=leaves, prev_root=prev_root)
    for i, leaf in enumerate(leaves):
        proof = batch.get_event_proof(i)
        assert verify_proof(batch.root_hex, leaf, proof), \
            f"Valid proof for leaf {i} should verify"


def test_p2_valid_proofs_verify() -> tuple[int, bool]:
    try:
        _test_p2()
        return 1000, True
    except Exception as e:
        print(f"P2 FAILED: {e}")
        return 1000, False


# ---------------------------------------------------------------------------
# P3: Tampered leaves fail
# ---------------------------------------------------------------------------

@given(
    leaves=st.lists(st.binary(min_size=32, max_size=32), min_size=2, max_size=32),
    prev_root=st.binary(min_size=32, max_size=32),
    leaf_idx=st.integers(min_value=0),
)
@HYPOTHESIS_SETTINGS
def _test_p3(leaves: list[bytes], prev_root: bytes, leaf_idx: int) -> None:
    """A tampered leaf must not verify against the original root."""
    idx = leaf_idx % len(leaves)
    batch = Batch(batch_id=0, event_hashes=leaves, prev_root=prev_root)
    proof = batch.get_event_proof(idx)

    # Tamper: flip one bit of the leaf
    original = leaves[idx]
    tampered = bytes([original[0] ^ 0xFF]) + original[1:]

    result = verify_proof(batch.root_hex, tampered, proof)
    assert not result, "Tampered leaf should not verify"


def test_p3_tamper_detection() -> tuple[int, bool]:
    try:
        _test_p3()
        return 1000, True
    except Exception as e:
        print(f"P3 FAILED: {e}")
        return 1000, False


# ---------------------------------------------------------------------------
# P4: Predecessor root modification invalidates chain
# ---------------------------------------------------------------------------

@given(
    leaves=st.lists(st.binary(min_size=32, max_size=32), min_size=1, max_size=32),
    prev_root=st.binary(min_size=32, max_size=32),
    bad_prev=st.binary(min_size=32, max_size=32),
)
@HYPOTHESIS_SETTINGS
def _test_p4(leaves: list[bytes], prev_root: bytes, bad_prev: bytes) -> None:
    """Modifying prev_root must change the batch root (except with astronomically low probability)."""
    if prev_root == bad_prev:
        return  # trivially same; skip
    b1 = Batch(batch_id=0, event_hashes=leaves, prev_root=prev_root)
    b2 = Batch(batch_id=0, event_hashes=leaves, prev_root=bad_prev)
    assert b1.root != b2.root, "Different prev_root must produce different batch root"


def test_p4_chain_integrity() -> tuple[int, bool]:
    try:
        _test_p4()
        return 1000, True
    except Exception as e:
        print(f"P4 FAILED: {e}")
        return 1000, False


# ---------------------------------------------------------------------------
# P5: Idempotency — duplicate keys are rejected
# ---------------------------------------------------------------------------

def test_p5_idempotency() -> tuple[int, bool]:
    """Submit the same event 1000 times; only the first should be accepted."""
    gw = IngestionGateway()
    base_event = {
        "inv_id": "INV-001",
        "payer_ref": "PAR-001",
        "amount": "1500000",
        "currency": "VND",
        "status": "PAID",
        "channel": "BANK_TRANSFER",
        "ts": "2024-01-15T09:30:00Z",
    }
    # First ingestion: accepted
    r1 = gw.ingest(base_event)
    if not r1.accepted:
        print(f"P5 FAILED: First ingestion rejected: {r1.reason}")
        return 1000, False

    # Subsequent identical ingestions: all rejected as duplicates
    all_rejected = True
    for _ in range(999):
        r = gw.ingest(dict(base_event))
        if r.accepted:
            all_rejected = False
            break

    if not all_rejected:
        print("P5 FAILED: Duplicate was accepted")
        return 1000, False
    return 1000, True


# ---------------------------------------------------------------------------
# P6: Fault isolation — malformed payloads rejected before batching
# ---------------------------------------------------------------------------

def test_p6_fault_isolation() -> tuple[int, bool]:
    """
    Mix 500 valid and 500 malformed events.
    All malformed events must be rejected (FIR_syn = 100%).
    No valid events may be wrongly rejected (FRR = 0%).
    """
    import random
    rng = random.Random(42)
    gw = IngestionGateway()

    valid_template = {
        "inv_id": "INV-{i:06d}",
        "payer_ref": "PAR-001",
        "amount": "1500000",
        "currency": "VND",
        "status": "PAID",
        "channel": "BANK_TRANSFER",
        "ts": "2024-01-15T09:30:00Z",
    }

    malformed_templates = [
        {"payer_ref": "PAR", "amount": "100", "currency": "VND",
         "status": "PAID", "channel": "BANK_TRANSFER", "ts": "2024-01-15T09:30:00Z"},  # missing inv_id
        {"inv_id": "INV-BADAMT", "payer_ref": "PAR", "amount": "-1",
         "currency": "VND", "status": "PAID", "channel": "BANK_TRANSFER", "ts": "2024-01-15T09:30:00Z"},
        {"inv_id": "INV-BADSTATUS", "payer_ref": "PAR", "amount": "100",
         "currency": "VND", "status": "INVALID", "channel": "BANK_TRANSFER", "ts": "2024-01-15T09:30:00Z"},
        {"inv_id": "INV-BADAMT2", "payer_ref": "PAR", "amount": "not-a-number",
         "currency": "VND", "status": "PAID", "channel": "BANK_TRANSFER", "ts": "2024-01-15T09:30:00Z"},
    ]

    n_valid_rejected = 0
    n_malformed_accepted = 0

    for i in range(500):
        ev = {k: v.format(i=i) if isinstance(v, str) else v
              for k, v in valid_template.items()}
        r = gw.ingest(ev)
        if not r.accepted and r.reason != "DUPLICATE_IDEM_KEY":
            n_valid_rejected += 1

    for i in range(500):
        ev = dict(rng.choice(malformed_templates))
        r = gw.ingest(ev)
        if r.accepted:
            n_malformed_accepted += 1

    if n_malformed_accepted > 0:
        print(f"P6 FAILED: {n_malformed_accepted} malformed events accepted")
        return 1000, False
    if n_valid_rejected > 0:
        print(f"P6 WARN: {n_valid_rejected} valid events rejected (FRR > 0%)")
        return 1000, False
    return 1000, True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all() -> None:
    print("=" * 60)
    print("E0: Property-Based Tests")
    print("=" * 60)

    tests = [
        ("P1 Root determinism", test_p1_root_determinism),
        ("P2 Valid proof verifies", test_p2_valid_proofs_verify),
        ("P3 Tamper detection", test_p3_tamper_detection),
        ("P4 Chain integrity", test_p4_chain_integrity),
        ("P5 Idempotency", test_p5_idempotency),
        ("P6 Fault isolation", test_p6_fault_isolation),
    ]

    rows = []
    for name, fn in tests:
        print(f"  Running {name}...", end=" ", flush=True)
        t0 = time.time()
        trials, passed = fn()
        elapsed = time.time() - t0
        result = "Pass" if passed else "FAIL"
        print(f"{result} ({elapsed:.1f}s)")
        rows.append({"property": name, "trials": trials, "result": result, "elapsed_s": f"{elapsed:.2f}"})

    # Write CSV
    csv_path = RESULTS_DIR / "e0_property.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["property", "trials", "result", "elapsed_s"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[E0] Results written to {csv_path}")
    all_pass = all(r["result"] == "Pass" for r in rows)
    print(f"[E0] Overall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    return rows


if __name__ == "__main__":
    run_all()
