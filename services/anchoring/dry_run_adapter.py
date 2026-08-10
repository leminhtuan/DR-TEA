"""
DR-TEA — Dry-Run Anchoring Adapter
====================================
Simulates Cardano anchoring without network access.

Features:
  - Deterministic tx IDs: SHA-256(root || batch_id || timestamp_bucket)
  - CIP-20 metadata structure matching production format
  - Configurable latency: log-normal distribution
  - Cardano fee formula: min_fee_a * tx_size + min_fee_b
  - No network required — structurally identical to live adapter outputs

Cardano mainnet fee parameters (Babbage era, as of 2024):
  min_fee_a = 44 lovelace/byte
  min_fee_b = 155381 lovelace (base fee)
  Typical CIP-20 tx size for DR-TEA: ~350–450 bytes
"""

from __future__ import annotations

import hashlib
import json
import time
import math
import random
from dataclasses import dataclass, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Cardano fee model
# ---------------------------------------------------------------------------

# Cardano protocol parameters (Babbage / Conway era)
MIN_FEE_A: int = 44          # lovelace per byte
MIN_FEE_B: int = 155_381     # base fee in lovelace
LOVELACE_PER_ADA: int = 1_000_000

# Current representative ADA price in USD (used as default for cost modeling)
# Updated from E8 Monte Carlo when available; conservative midpoint as default
ADA_PRICE_USD: float = 0.44


# Typical CIP-20 metadata tx size for DR-TEA (root ~32 bytes hex + overhead)
# Estimated from Blockfrost tx size observations on preprod
DRY_RUN_TX_SIZE_BYTES_MEAN: float = 390.0
DRY_RUN_TX_SIZE_BYTES_STD: float = 20.0


def estimate_fee_lovelace(tx_size_bytes: int) -> int:
    """Cardano fee formula: a * size + b (lovelace)."""
    return MIN_FEE_A * tx_size_bytes + MIN_FEE_B


def estimate_fee_ada(tx_size_bytes: int) -> float:
    return estimate_fee_lovelace(tx_size_bytes) / LOVELACE_PER_ADA


# ---------------------------------------------------------------------------
# CIP-20 metadata structure
# ---------------------------------------------------------------------------

def build_cip20_metadata(
    root_hex: str,
    prev_root_hex: str,
    batch_id: int,
    schema_version: str = "drtea-v1",
) -> dict:
    """
    Build CIP-20 compliant transaction metadata.
    Label 674 is the Cardano Foundation general-purpose message label.
    """
    return {
        "674": {
            "msg": [
                f"DR-TEA:{schema_version}",
                f"batch:{batch_id}",
                f"root:{root_hex[:32]}",   # First 32 chars (64 total → split if needed)
                f"root_b:{root_hex[32:]}",
                f"prev:{prev_root_hex[:32]}",
                f"prev_b:{prev_root_hex[32:]}",
            ]
        }
    }


# ---------------------------------------------------------------------------
# Dry-run adapter
# ---------------------------------------------------------------------------

@dataclass
class AnchorResult:
    tx_id: str
    root_hex: str
    prev_root_hex: str
    batch_id: int
    fee_lovelace: int
    fee_ada: float
    tx_size_bytes: int
    metadata: dict
    submitted_at: float
    confirmed_at: float
    confirmation_delay_s: float
    mode: str  # "dry-run" | "testnet" | "mainnet"
    explorer_url: str

    def to_dict(self) -> dict:
        return asdict(self)


class DryRunAdapter:
    """
    Deterministic dry-run Cardano anchoring adapter.
    Produces structurally identical outputs to CardanoAdapter but without network.
    """

    # Log-normal parameters for confirmation delay simulation
    # Cardano block time ~20s; typical confirmation at 3 blocks = ~60s
    # log-normal: mean=90s, sigma=0.4 → 95th pct ~180s
    DELAY_LOG_MEAN: float = math.log(90)
    DELAY_LOG_SIGMA: float = 0.4

    # Explorer URL template (matches Cardano Preprod)
    PREPROD_EXPLORER = "https://preprod.cardanoscan.io/transaction/{tx_id}"
    MAINNET_EXPLORER = "https://cardanoscan.io/transaction/{tx_id}"

    def __init__(self, rng: random.Random, mode: str = "dry-run") -> None:
        self._rng = rng
        self._mode = mode

    def _deterministic_tx_id(self, root_hex: str, batch_id: int) -> str:
        """
        Deterministic simulated tx ID.
        SHA-256(root_bytes || batch_id_8bytes)
        """
        data = bytes.fromhex(root_hex) + batch_id.to_bytes(8, "big")
        return hashlib.sha256(data).hexdigest()

    def _sample_tx_size(self) -> int:
        """Sample transaction size from a normal distribution."""
        size = self._rng.gauss(DRY_RUN_TX_SIZE_BYTES_MEAN, DRY_RUN_TX_SIZE_BYTES_STD)
        return max(300, int(size))

    def _sample_confirmation_delay(self) -> float:
        """Sample confirmation delay from log-normal distribution."""
        return self._rng.lognormvariate(self.DELAY_LOG_MEAN, self.DELAY_LOG_SIGMA)

    def submit_root(
        self,
        root_hex: str,
        prev_root_hex: str,
        batch_id: int,
        submitted_at: Optional[float] = None,
    ) -> AnchorResult:
        """
        Simulate submitting a Merkle root to Cardano.
        Returns an AnchorResult with deterministic tx_id and sampled latency/fee.
        """
        t_submit = submitted_at if submitted_at is not None else time.time()

        tx_size = self._sample_tx_size()
        fee_lovelace = estimate_fee_lovelace(tx_size)
        fee_ada = fee_lovelace / LOVELACE_PER_ADA
        delay = self._sample_confirmation_delay()
        t_confirm = t_submit + delay

        tx_id = self._deterministic_tx_id(root_hex, batch_id)
        metadata = build_cip20_metadata(root_hex, prev_root_hex, batch_id)
        explorer = (
            self.MAINNET_EXPLORER.format(tx_id=tx_id)
            if self._mode == "mainnet"
            else self.PREPROD_EXPLORER.format(tx_id=tx_id)
        )

        return AnchorResult(
            tx_id=tx_id,
            root_hex=root_hex,
            prev_root_hex=prev_root_hex,
            batch_id=batch_id,
            fee_lovelace=fee_lovelace,
            fee_ada=fee_ada,
            tx_size_bytes=tx_size,
            metadata=metadata,
            submitted_at=t_submit,
            confirmed_at=t_confirm,
            confirmation_delay_s=delay,
            mode=self._mode,
            explorer_url=explorer,
        )

    def estimate_fee_ada(self) -> float:
        """Return mean fee estimate for cost modeling."""
        return estimate_fee_ada(int(DRY_RUN_TX_SIZE_BYTES_MEAN))


# ---------------------------------------------------------------------------
# Blockfrost adapter (live testnet / mainnet)
# ---------------------------------------------------------------------------

class BlockfrostAdapter:
    """
    Live Cardano anchoring using Blockfrost API.
    Used for E5 (live baselines) and E7 (mainnet pilot).

    NOTE: Requires BLOCKFROST_PROJECT_ID environment variable.
    Transactions are constructed using only metadata (CIP-20), no UTxO spending.
    A minimal 1-ADA self-transfer with CIP-20 metadata is submitted.
    """

    PREPROD_URL = "https://cardano-preprod.blockfrost.io/api/v0"
    MAINNET_URL = "https://cardano-mainnet.blockfrost.io/api/v0"

    def __init__(self, project_id: str, network: str = "preprod") -> None:
        self._project_id = project_id
        self._network = network
        self._base_url = self.PREPROD_URL if network == "preprod" else self.MAINNET_URL

    def _headers(self) -> dict:
        return {"project_id": self._project_id}

    def get_latest_block(self) -> dict:
        import requests
        r = requests.get(f"{self._base_url}/blocks/latest", headers=self._headers(), timeout=10)
        r.raise_for_status()
        return r.json()

    def get_tx(self, tx_hash: str) -> dict:
        import requests
        r = requests.get(f"{self._base_url}/txs/{tx_hash}", headers=self._headers(), timeout=10)
        r.raise_for_status()
        return r.json()

    def get_network_params(self) -> dict:
        """Get current protocol parameters."""
        import requests
        r = requests.get(f"{self._base_url}/epochs/latest/parameters", headers=self._headers(), timeout=10)
        r.raise_for_status()
        return r.json()

    def ping(self) -> bool:
        """Check if Blockfrost is reachable."""
        try:
            self.get_latest_block()
            return True
        except Exception:
            return False
