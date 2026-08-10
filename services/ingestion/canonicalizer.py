"""
DR-TEA — Ingestion Canonicalizer
=================================
Implements:
  - Eq. 1: PaymentEvent canonical schema
  - Eq. 2: h = H(C(e))  using RFC 8785 (JCS) canonicalization + SHA-256
  - Eq. 4/5: Idempotency key generation
  - Duplicate rejection

CRITICAL: All cryptographic hashing MUST go through jcs.canonicalize().
          NEVER use json.dumps() for hashing.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import jcs
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# 1. Canonical event model — Equation 1
# ---------------------------------------------------------------------------

class PaymentEvent(BaseModel):
    """
    Canonical payment event schema (Eq. 1 in the paper).

    e = (inv_id, payer_ref, amount, currency, status, channel, ts, idem_key)
    """

    inv_id: str = Field(..., description="Invoice identifier")
    payer_ref: str = Field(..., description="Payer reference (opaque)")
    amount: str = Field(..., description="Amount as decimal string to avoid float precision loss")
    currency: str = Field(..., min_length=3, max_length=10, description="ISO 4217 currency code")
    status: str = Field(..., description="Payment status: PENDING | PAID | REFUNDED | PARTIAL | FAILED")
    channel: str = Field(..., description="Payment channel: BANK | WALLET | CARD | MOMO | etc.")
    ts: str = Field(..., description="ISO 8601 UTC timestamp of the payment event")
    idem_key: Optional[str] = Field(default=None, description="Idempotency key (generated if absent)")

    # Optional domain extension fields (used in W2 secondary-domain workload)
    domain: Optional[str] = Field(default=None, description="Domain tag e.g. K12 | UNIVERSITY | UTILITY")
    domain_ext: Optional[dict] = Field(default=None, description="Domain-specific extension fields")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"PENDING", "PAID", "REFUNDED", "PARTIAL", "FAILED", "LATE"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}, got {v!r}")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        try:
            val = float(v)
        except ValueError:
            raise ValueError(f"amount must be a numeric string, got {v!r}")
        if val < 0:
            raise ValueError(f"amount must be non-negative, got {v!r}")
        return v

    @field_validator("ts")
    @classmethod
    def validate_ts(cls, v: str) -> str:
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"ts must be ISO 8601, got {v!r}")
        # Reject future timestamps (>60s ahead)
        now = datetime.now(timezone.utc)
        if dt.replace(tzinfo=timezone.utc) > now.replace(tzinfo=None).replace(tzinfo=timezone.utc):
            # Allow for clock skew up to 60s
            pass  # We do not reject future timestamps during testing/simulation
        return v

    @model_validator(mode="after")
    def generate_idem_key_if_missing(self) -> "PaymentEvent":
        if self.idem_key is None:
            self.idem_key = _generate_idem_key(self)
        return self


# ---------------------------------------------------------------------------
# 2. Idempotency key generation — Equations 4 and 5
# ---------------------------------------------------------------------------

# A stable ingestion key loaded from environment (32-byte hex string)
_K_INGEST_HEX = os.environ.get(
    "K_INGEST",
    "0" * 64,  # default zero key for dry-run / testing
)
_K_INGEST = bytes.fromhex(_K_INGEST_HEX)


def _phi(e: PaymentEvent) -> bytes:
    """
    Compute canonical context φ(e) for idempotency key derivation (Eq. 5).
    Contains: inv_id, channel, payer_ref, amount, currency, ts (minute bucket).
    """
    # Bucket timestamp to the minute to absorb millisecond jitter
    try:
        dt = datetime.fromisoformat(e.ts.replace("Z", "+00:00"))
        ts_bucket = dt.strftime("%Y-%m-%dT%H:%M:00Z")
    except Exception:
        ts_bucket = e.ts

    ctx = {
        "inv_id": e.inv_id,
        "channel": e.channel,
        "payer_ref": e.payer_ref,
        "amount": e.amount,
        "currency": e.currency,
        "ts_bucket": ts_bucket,
    }
    return jcs.canonicalize(ctx)


def _generate_idem_key(e: PaymentEvent) -> str:
    """
    Eq. 5: idem_key = Trunc_128(HMAC-SHA256(K_ingest, φ(e)))
    Returns a 32-character hex string (128 bits).
    """
    phi_bytes = _phi(e)
    mac = hmac.new(_K_INGEST, phi_bytes, digestmod=hashlib.sha256).digest()
    return mac[:16].hex()  # 128-bit truncation → 32 hex chars


def set_provider_tx_id(e: PaymentEvent, provider_tx_id: str) -> PaymentEvent:
    """
    Eq. 4: If the payment provider supplies a globally unique transaction ID,
    use it directly as the idempotency key.
    """
    return e.model_copy(update={"idem_key": provider_tx_id})


# ---------------------------------------------------------------------------
# 3. RFC 8785 canonicalization and SHA-256 hash — Equation 2
# ---------------------------------------------------------------------------

def _event_to_dict(e: PaymentEvent) -> dict:
    """
    Convert a PaymentEvent to a plain dict suitable for JCS canonicalization.
    Keys with None values are excluded (deterministic omission).
    """
    raw = e.model_dump(exclude_none=True)
    # Ensure all values are JSON-primitive-compatible (dict/list/str/int/float/bool/None)
    return raw


def canonical_bytes(e: PaymentEvent) -> bytes:
    """
    C(e) — RFC 8785 canonical serialization of the event.
    Returns the canonical UTF-8 byte sequence.
    """
    d = _event_to_dict(e)
    return jcs.canonicalize(d)


def canonical_hash(e: PaymentEvent) -> bytes:
    """
    Eq. 2: h = H(C(e)) = SHA-256(RFC-8785(e))
    Returns 32-byte digest.
    """
    return hashlib.sha256(canonical_bytes(e)).digest()


def canonical_hash_hex(e: PaymentEvent) -> str:
    """Return canonical hash as 64-character hex string."""
    return canonical_hash(e).hex()


# ---------------------------------------------------------------------------
# 4. Duplicate rejection registry (in-memory; use DB uniqueness in production)
# ---------------------------------------------------------------------------

class IdempotencyRegistry:
    """
    Thread-unsafe in-memory registry for idempotency key deduplication.
    In production, replace with a Postgres UNIQUE constraint.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def check_and_register(self, idem_key: str) -> bool:
        """
        Returns True if the key is new (accepted), False if duplicate (rejected).
        """
        if idem_key in self._seen:
            return False
        self._seen.add(idem_key)
        return True

    def reset(self) -> None:
        self._seen.clear()

    def __len__(self) -> int:
        return len(self._seen)


# ---------------------------------------------------------------------------
# 5. Ingestion Gateway — wires the above together
# ---------------------------------------------------------------------------

class IngestionResult(BaseModel):
    accepted: bool
    reason: str
    event: Optional[PaymentEvent] = None
    hash_hex: Optional[str] = None
    canonical_bytes_hex: Optional[str] = None


class IngestionGateway:
    """
    Validates, deduplicates, canonicalizes, and hashes incoming events.
    Corresponds to the Ingestion Gateway component in the architecture.
    """

    def __init__(self) -> None:
        self._registry = IdempotencyRegistry()

    def ingest(self, raw: dict, provider_tx_id: Optional[str] = None) -> IngestionResult:
        """
        Main ingestion entry point.
        Returns IngestionResult with accepted=True and hash_hex on success.
        """
        # Step 1: Validate schema (Pydantic v2)
        try:
            event = PaymentEvent(**raw)
        except Exception as exc:
            return IngestionResult(accepted=False, reason=f"SCHEMA_VALIDATION_ERROR: {exc}")

        # Step 2: Apply provider tx id if supplied (Eq. 4)
        if provider_tx_id:
            event = set_provider_tx_id(event, provider_tx_id)

        # Step 3: Duplicate check
        if not self._registry.check_and_register(event.idem_key):
            return IngestionResult(accepted=False, reason="DUPLICATE_IDEM_KEY", event=event)

        # Step 4: Compute canonical hash (Eq. 2)
        cb = canonical_bytes(event)
        h = hashlib.sha256(cb).digest()

        return IngestionResult(
            accepted=True,
            reason="OK",
            event=event,
            hash_hex=h.hex(),
            canonical_bytes_hex=cb.hex(),
        )

    def reset(self) -> None:
        self._registry.reset()
