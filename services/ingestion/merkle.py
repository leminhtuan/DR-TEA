"""
DR-TEA — Binary Merkle Tree with Predecessor-Root Chaining
===========================================================
Implements:
  - Eq. 6: r_j = MerkleRoot(B_j || r_{j-1})   (predecessor chaining)
  - Eq. 7: Verify(r_j, H(e), π_e) ∈ {true, false}

Standard binary Merkle tree with SHA-256. Pairs are hashed in (left, right)
order without sorting, preserving event sequence determinism.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GENESIS_PREV_ROOT = b"\x00" * 32  # 32 zero bytes for the first batch


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _node_hash(left: bytes, right: bytes) -> bytes:
    """Standard Merkle node hash: SHA256(left || right)."""
    return _sha256(left + right)


def _leaf_hash(data: bytes) -> bytes:
    """Leaf hash: SHA256(0x00 || data) — domain-separated from node hashes."""
    return _sha256(b"\x00" + data)


def _internal_hash(left: bytes, right: bytes) -> bytes:
    """Internal node hash: SHA256(0x01 || left || right)."""
    return _sha256(b"\x01" + left + right)


# ---------------------------------------------------------------------------
# Merkle tree builder
# ---------------------------------------------------------------------------

@dataclass
class MerkleProof:
    """
    A Merkle inclusion proof for a single leaf.

    path: list of {"sibling": hex_str, "position": "left"|"right"}
          where "position" is the position of the SIBLING relative to the node.
    leaf_hash: hex string of the leaf hash
    root: hex string of the Merkle root
    leaf_index: int, 0-based position in the original leaf list
    """
    leaf_hash: str
    root: str
    leaf_index: int
    path: list[dict]  # [{"sibling": hex, "position": "left"|"right"}, ...]

    def to_dict(self) -> dict:
        return {
            "leaf_hash": self.leaf_hash,
            "root": self.root,
            "leaf_index": self.leaf_index,
            "path": self.path,
        }

    def serialized_bytes(self) -> bytes:
        """Serialized proof for size measurement (S_π metric)."""
        return json.dumps(self.to_dict(), separators=(",", ":")).encode()

    def size_bytes(self) -> int:
        return len(self.serialized_bytes())


def _build_tree(leaves: list[bytes]) -> list[list[bytes]]:
    """
    Build a full binary Merkle tree from a list of leaf byte values.
    Returns a list of levels, level[0] being the leaf level.
    If the number of leaves is odd, the last leaf is duplicated.
    """
    if not leaves:
        raise ValueError("Cannot build Merkle tree with zero leaves")

    current: list[bytes] = [_leaf_hash(leaf) for leaf in leaves]
    levels: list[list[bytes]] = [current]

    while len(current) > 1:
        if len(current) % 2 == 1:
            current = current + [current[-1]]  # duplicate last node
        next_level: list[bytes] = []
        for i in range(0, len(current), 2):
            next_level.append(_internal_hash(current[i], current[i + 1]))
        levels.append(next_level)
        current = next_level

    return levels


def compute_merkle_root(leaves: list[bytes]) -> bytes:
    """Compute the Merkle root of an ordered list of byte leaves."""
    if not leaves:
        raise ValueError("Cannot compute Merkle root of empty list")
    levels = _build_tree(leaves)
    return levels[-1][0]


def generate_proof(leaves: list[bytes], leaf_index: int) -> MerkleProof:
    """
    Generate an inclusion proof for the leaf at leaf_index.

    Args:
        leaves: ordered list of raw leaf byte values (before hashing)
        leaf_index: 0-based index of the leaf to prove

    Returns:
        MerkleProof with the path from leaf to root
    """
    if not leaves:
        raise ValueError("Empty leaf list")
    if leaf_index < 0 or leaf_index >= len(leaves):
        raise IndexError(f"leaf_index {leaf_index} out of range [0, {len(leaves)})")

    levels = _build_tree(leaves)
    root_hex = levels[-1][0].hex()
    leaf_hash_hex = levels[0][leaf_index].hex()

    path: list[dict] = []
    idx = leaf_index

    for level in levels[:-1]:
        # Pad level if odd (mirrors _build_tree behaviour)
        padded = level if len(level) % 2 == 0 else level + [level[-1]]
        if idx % 2 == 0:
            sibling_idx = idx + 1
            sibling_pos = "right"
        else:
            sibling_idx = idx - 1
            sibling_pos = "left"
        path.append({
            "sibling": padded[sibling_idx].hex(),
            "position": sibling_pos,
        })
        idx //= 2

    return MerkleProof(
        leaf_hash=leaf_hash_hex,
        root=root_hex,
        leaf_index=leaf_index,
        path=path,
    )


def verify_proof(root_hex: str, leaf_bytes: bytes, proof: MerkleProof) -> bool:
    """
    Eq. 7: Verify(r_j, H(e), π_e) ∈ {true, false}

    Recomputes root from leaf_bytes + proof path and compares to root_hex.
    """
    current = _leaf_hash(leaf_bytes)

    for step in proof.path:
        sibling = bytes.fromhex(step["sibling"])
        if step["position"] == "right":
            current = _internal_hash(current, sibling)
        else:
            current = _internal_hash(sibling, current)

    return current.hex() == root_hex


# ---------------------------------------------------------------------------
# Batch with predecessor chaining — Equation 6
# ---------------------------------------------------------------------------

@dataclass
class Batch:
    """
    A batch of event hashes with predecessor chaining.

    r_j = MerkleRoot(B_j || r_{j-1})

    The predecessor root r_{j-1} is prepended as the FIRST leaf of the batch.
    This makes r_{j-1} provable in the Merkle tree and chains batches.
    """
    batch_id: int
    event_hashes: list[bytes]          # ordered event hashes h_1..h_m
    prev_root: bytes                   # r_{j-1}; GENESIS_PREV_ROOT for j=0
    root: bytes = field(init=False)
    leaves: list[bytes] = field(init=False)  # the full leaf list (prev_root first)

    def __post_init__(self) -> None:
        # Eq. 6: r_j = MerkleRoot([r_{j-1}] + B_j)
        self.leaves = [self.prev_root] + self.event_hashes
        self.root = compute_merkle_root(self.leaves)

    @property
    def root_hex(self) -> str:
        return self.root.hex()

    @property
    def prev_root_hex(self) -> str:
        return self.prev_root.hex()

    def size(self) -> int:
        """Number of payment events in this batch (not counting prev_root leaf)."""
        return len(self.event_hashes)

    def get_event_proof(self, event_index: int) -> MerkleProof:
        """
        Generate a Merkle proof for the event at event_index (0-based within the batch).
        Note: leaf 0 in self.leaves is the prev_root; event leaf i is at position i+1.
        """
        leaf_position = event_index + 1  # +1 because leaf 0 is prev_root
        return generate_proof(self.leaves, leaf_position)

    def verify_event(self, event_hash: bytes, proof: MerkleProof) -> bool:
        """Verify an event's inclusion in this batch."""
        return verify_proof(self.root_hex, event_hash, proof)


# ---------------------------------------------------------------------------
# Batch Commitment Engine
# ---------------------------------------------------------------------------

class BatchCommitmentEngine:
    """
    Groups event hashes into ordered batches and computes chained roots.
    Corresponds to the Batch Commitment Engine component in Section IV.
    """

    def __init__(self) -> None:
        self._pending: list[bytes] = []
        self._prev_root: bytes = GENESIS_PREV_ROOT
        self._batch_counter: int = 0
        self._committed_batches: list[Batch] = []

    def add_event_hash(self, event_hash: bytes) -> None:
        """Add a single event hash to the pending batch."""
        if len(event_hash) != 32:
            raise ValueError(f"Event hash must be 32 bytes, got {len(event_hash)}")
        self._pending.append(event_hash)

    def add_event_hashes(self, event_hashes: list[bytes]) -> None:
        for h in event_hashes:
            self.add_event_hash(h)

    def pending_size(self) -> int:
        return len(self._pending)

    def commit_batch(self) -> Optional[Batch]:
        """
        Close the current pending batch and compute its chained root.
        Returns None if no events are pending.
        """
        if not self._pending:
            return None

        batch = Batch(
            batch_id=self._batch_counter,
            event_hashes=list(self._pending),
            prev_root=self._prev_root,
        )
        self._prev_root = batch.root
        self._batch_counter += 1
        self._pending.clear()
        self._committed_batches.append(batch)
        return batch

    def commit_if_full(self, max_size: int) -> Optional[Batch]:
        """Commit if pending size has reached max_size."""
        if self._pending_size_int() >= max_size:
            return self.commit_batch()
        return None

    def _pending_size_int(self) -> int:
        return len(self._pending)

    @property
    def committed_batches(self) -> list[Batch]:
        return list(self._committed_batches)

    @property
    def latest_root(self) -> bytes:
        return self._prev_root

    def reset(self) -> None:
        self._pending.clear()
        self._prev_root = GENESIS_PREV_ROOT
        self._batch_counter = 0
        self._committed_batches.clear()
