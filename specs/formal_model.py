"""
DR-TEA — Formal Model Specification (IEEE Access)
=================================================
Formal mathematical equations and cryptographic invariants:

1. Canonical Payment Event Schema:
   e = (inv_id, payer_ref, amount, currency, status, channel, ts, idem_key)  [Eq. 1]

2. Cryptographic Digest:
   h = H(C(e)) = SHA256(RFC8785(e))                                          [Eq. 2]

3. Dual-Receipt Signature:
   σ = Sign(SK_issuer, h || ts || meta)                                      [Eq. 3]

4. Idempotency Key Derivation:
   idem_key = Trunc_128(HMAC_SHA256(K_ingest, φ(e)))                        [Eq. 5]
   where φ(e) = JCS({inv_id, channel, payer_ref, amount, currency, ts_bucket})

5. Chained Batch Commitment:
   r_j = MerkleRoot([r_{j-1}] + B_j)                                         [Eq. 6]
   where r_{-1} = 0^{32} (GENESIS_PREV_ROOT)
   B_j = [h_{j,1}, h_{j,2}, ..., h_{j,m}]

6. Merkle Inclusion Verification:
   Verify(r_j, h, π_e) ∈ {true, false}                                       [Eq. 7]
"""

from __future__ import annotations
import hashlib
from typing import List, Tuple
import jcs

GENESIS_PREV_ROOT: bytes = b"\x00" * 32

def leaf_hash(data: bytes) -> bytes:
    """Domain-separated leaf hash: SHA256(0x00 || data)"""
    return hashlib.sha256(b"\x00" + data).digest()

def internal_hash(left: bytes, right: bytes) -> bytes:
    """Domain-separated internal node hash: SHA256(0x01 || left || right)"""
    return hashlib.sha256(b"\x01" + left + right).digest()

def compute_merkle_root(leaves: List[bytes]) -> bytes:
    """Compute binary Merkle root over list of raw byte leaves."""
    if not leaves:
        raise ValueError("Cannot compute Merkle root of empty leaf list")
    current = [leaf_hash(leaf) for leaf in leaves]
    while len(current) > 1:
        if len(current) % 2 == 1:
            current.append(current[-1])
        next_level = []
        for i in range(0, len(current), 2):
            next_level.append(internal_hash(current[i], current[i + 1]))
        current = next_level
    return current[0]

def compute_chained_batch_root(event_hashes: List[bytes], prev_root: bytes) -> bytes:
    """
    Eq. 6: r_j = MerkleRoot([r_{j-1}] + B_j)
    Predecessor root r_{j-1} is placed as the first leaf (index 0).
    """
    leaves = [prev_root] + event_hashes
    return compute_merkle_root(leaves)
