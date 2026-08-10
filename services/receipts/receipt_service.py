"""
DR-TEA — Receipt Signing Service
=================================
Implements Equations (8) and (9) from the paper:

  R_SSC(e)    = Sign_SSC(h || seq || ts)
  R_school(e) = Sign_school(h || seq || ts)

Uses Ed25519 via the `cryptography` library.
Receipts are written to an in-memory append-only log.
For production, replace the log with PostgreSQL.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from threading import Lock
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    PrivateFormat,
    NoEncryption,
)
from cryptography.exceptions import InvalidSignature


# ---------------------------------------------------------------------------
# Key management helpers
# ---------------------------------------------------------------------------

def generate_ed25519_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Generate a fresh Ed25519 key pair."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def private_key_to_hex(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    return raw.hex()


def public_key_to_hex(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return raw.hex()


def private_key_from_hex(hex_str: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(hex_str))


def public_key_from_hex(hex_str: str) -> Ed25519PublicKey:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import load_raw_public_key
    # Use low-level raw bytes loading
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    raw = bytes.fromhex(hex_str)
    return Ed25519PrivateKey.from_private_bytes(raw).public_key()  # fallback workaround


# ---------------------------------------------------------------------------
# Receipt data model
# ---------------------------------------------------------------------------

@dataclass
class Receipt:
    """
    A signed receipt for a single payment event.

    Fields correspond to Eq. 8/9:
      R_SSC(e) = Sign_SSC(h || seq || ts)
    """
    event_hash_hex: str          # h — canonical hash of the event
    seq: int                     # monotonic sequence number
    ts_issued: float             # Unix timestamp of receipt issuance
    signer_id: str               # "SSC" or "SCHOOL:<school_id>"
    signature_hex: str           # Ed25519 signature (hex)
    provisional_no_cosign: bool  # True if school co-signature is missing
    inv_id: str                  # Invoice ID for quick lookup
    batch_id: Optional[int] = None  # Filled when event is committed to a batch
    anchor_tx_id: Optional[str] = None  # Filled when batch is anchored

    def to_dict(self) -> dict:
        return asdict(self)

    def signed_message(self) -> bytes:
        """
        Reconstruct the signed message: h || seq (8 bytes big-endian) || ts (8 bytes big-endian).
        This is what was signed and must be reproduced for verification.
        """
        h_bytes = bytes.fromhex(self.event_hash_hex)
        seq_bytes = self.seq.to_bytes(8, "big")
        # ts as microseconds (integer)
        ts_int = int(self.ts_issued * 1_000_000)
        ts_bytes = ts_int.to_bytes(8, "big")
        return h_bytes + seq_bytes + ts_bytes


def _build_signed_message(event_hash_hex: str, seq: int, ts_issued: float) -> bytes:
    h_bytes = bytes.fromhex(event_hash_hex)
    seq_bytes = seq.to_bytes(8, "big")
    ts_int = int(ts_issued * 1_000_000)
    ts_bytes = ts_int.to_bytes(8, "big")
    return h_bytes + seq_bytes + ts_bytes


# ---------------------------------------------------------------------------
# Receipt Signing Service
# ---------------------------------------------------------------------------

class ReceiptSigningService:
    """
    Issues Ed25519-signed receipts for payment events.

    Usage:
        svc = ReceiptSigningService(ssc_private_key_hex, "SSC")
        receipt = svc.sign_receipt(event_hash_hex, inv_id)
    """

    def __init__(
        self,
        private_key_hex: str,
        signer_id: str,
    ) -> None:
        self._private_key = private_key_from_hex_raw(private_key_hex)
        self._signer_id = signer_id
        self._seq_counter: int = 0
        self._lock = Lock()
        self._receipt_log: list[Receipt] = []

    def _next_seq(self) -> int:
        with self._lock:
            self._seq_counter += 1
            return self._seq_counter

    def sign_receipt(
        self,
        event_hash_hex: str,
        inv_id: str,
        provisional_no_cosign: bool = False,
    ) -> Receipt:
        """
        Sign a receipt for a single event hash.
        Returns a Receipt object appended to the internal log.
        """
        seq = self._next_seq()
        ts = time.time()
        msg = _build_signed_message(event_hash_hex, seq, ts)
        sig = self._private_key.sign(msg)

        receipt = Receipt(
            event_hash_hex=event_hash_hex,
            seq=seq,
            ts_issued=ts,
            signer_id=self._signer_id,
            signature_hex=sig.hex(),
            provisional_no_cosign=provisional_no_cosign,
            inv_id=inv_id,
        )
        with self._lock:
            self._receipt_log.append(receipt)
        return receipt

    def get_log(self) -> list[Receipt]:
        with self._lock:
            return list(self._receipt_log)

    def reset(self) -> None:
        with self._lock:
            self._receipt_log.clear()
            self._seq_counter = 0


def private_key_from_hex_raw(hex_str: str) -> Ed25519PrivateKey:
    """Load Ed25519 private key from 32-byte hex string."""
    raw = bytes.fromhex(hex_str)
    return Ed25519PrivateKey.from_private_bytes(raw)


def verify_receipt_signature(receipt: Receipt, public_key_hex: str) -> bool:
    """Verify an Ed25519 receipt signature."""
    try:
        raw_pub = bytes.fromhex(public_key_hex)
        # Reconstruct public key from raw bytes
        priv = Ed25519PrivateKey.from_private_bytes(b"\x00" * 32)  # placeholder
        # Use cryptography's direct verification
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        pub = _load_raw_public_key(raw_pub)
        msg = receipt.signed_message()
        sig = bytes.fromhex(receipt.signature_hex)
        pub.verify(sig, msg)
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def _load_raw_public_key(raw_bytes: bytes) -> Ed25519PublicKey:
    """Load Ed25519 public key from raw 32-byte value."""
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    import struct
    # Build minimal DER encoding for Ed25519 public key
    # OID for Ed25519: 1.3.101.112
    oid = bytes.fromhex("302a300506032b6570032100")
    der = oid + raw_bytes
    return load_der_public_key(der)


# ---------------------------------------------------------------------------
# Dual-receipt issuer (SSC + optional school co-signer)
# ---------------------------------------------------------------------------

class DualReceiptIssuer:
    """
    Issues SSC primary receipt and optional school co-signature receipt.
    Implements the provisional_no_cosign fallback from Algorithm 1.
    """

    def __init__(
        self,
        ssc_private_key_hex: str,
        school_private_key_hex: Optional[str] = None,
        school_id: str = "SCHOOL_01",
    ) -> None:
        self._ssc_svc = ReceiptSigningService(ssc_private_key_hex, "SSC")
        self._school_svc: Optional[ReceiptSigningService] = None
        if school_private_key_hex:
            self._school_svc = ReceiptSigningService(
                school_private_key_hex, f"SCHOOL:{school_id}"
            )
        self._school_id = school_id

    def issue(
        self,
        event_hash_hex: str,
        inv_id: str,
        school_available: bool = True,
    ) -> tuple[Receipt, Optional[Receipt]]:
        """
        Issue SSC receipt and, if school is available, a school co-receipt.
        Returns (ssc_receipt, school_receipt_or_None).

        If school is unavailable, ssc_receipt has provisional_no_cosign=True.
        """
        school_receipt: Optional[Receipt] = None

        if school_available and self._school_svc is not None:
            ssc_receipt = self._ssc_svc.sign_receipt(
                event_hash_hex, inv_id, provisional_no_cosign=False
            )
            school_receipt = self._school_svc.sign_receipt(event_hash_hex, inv_id)
        else:
            # Fallback: SSC provisional receipt (Algorithm 1, step 7-8)
            ssc_receipt = self._ssc_svc.sign_receipt(
                event_hash_hex, inv_id, provisional_no_cosign=True
            )

        return ssc_receipt, school_receipt

    def get_ssc_log(self) -> list[Receipt]:
        return self._ssc_svc.get_log()

    def reset(self) -> None:
        self._ssc_svc.reset()
        if self._school_svc:
            self._school_svc.reset()
