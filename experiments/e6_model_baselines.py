"""
DR-TEA — E6: Model-Based Baselines (B4-B7)
============================================
B4: OpenTimestamps-style calendar anchoring
B5: Local CometBFT/Tendermint permissioned notary
B6: Ethereum L1 cost model
B7: EVM L2 / Algorand adapter (model-based estimate)

These are model-based estimates, NOT live measurements.
They are reported in a separate table from live baselines.

Outputs: results/e6_model.csv
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

DAILY_VOLUME = 5_000
ADA_PRICE_USD = 0.44

# ---------------------------------------------------------------------------
# B4: OpenTimestamps-style calendar anchoring
# ---------------------------------------------------------------------------

def model_b4_ots() -> dict:
    """
    OTS calendar model: one Bitcoin anchor per day.
    Cost = Bitcoin tx fee / (events per day).
    Bitcoin avg fee: $2-10 per tx.
    """
    BTC_FEE_MEAN_USD = 5.0
    BTC_FEE_STD_USD = 3.0
    # One anchor per day covers all events
    cost_per_event_usd = BTC_FEE_MEAN_USD / DAILY_VOLUME
    monthly_cost_usd = BTC_FEE_MEAN_USD * 30

    return {
        "baseline": "B4 OTS-style calendar",
        "model_type": "model-only",
        "anchoring_interval": "1 per day",
        "cost_model_assumptions": "BTC fee $5 mean, $3 std",
        "monthly_cost_usd_estimate": round(monthly_cost_usd, 2),
        "cost_per_event_usd_estimate": round(cost_per_event_usd, 6),
        "verify_latency_us": "N/A (Bitcoin Merkle proof ~400ms)",
        "tef_s_estimate": "~86400 (next daily anchor)",
        "public_verifiable": True,
        "omission_detectable": "No/Partial",
        "confirmation_threshold": "~6 blocks (~60 min)",
        "caveat": "No per-event proof; only batch-level calendar attestation",
    }


# ---------------------------------------------------------------------------
# B5: CometBFT permissioned notary
# ---------------------------------------------------------------------------

def model_b5_cometbft() -> dict:
    """
    Local 4-node CometBFT cluster.
    Consensus latency: ~200-500ms per block.
    Cost: infrastructure only (no per-tx gas).
    """
    CONSENSUS_LATENCY_MS_MEAN = 350
    CONSENSUS_LATENCY_MS_P95 = 600

    # Infrastructure cost (4 VMs × $50/mo)
    monthly_infra_usd = 4 * 50.0
    cost_per_1k_events_usd = (monthly_infra_usd / (DAILY_VOLUME * 30)) * 1000

    return {
        "baseline": "B5 CometBFT notary",
        "model_type": "model-only",
        "cluster_size": "4 nodes",
        "consensus_latency_mean_ms": CONSENSUS_LATENCY_MS_MEAN,
        "consensus_latency_p95_ms": CONSENSUS_LATENCY_MS_P95,
        "monthly_infra_cost_usd": monthly_infra_usd,
        "cost_per_1k_events_usd": round(cost_per_1k_events_usd, 4),
        "tef_s_estimate": CONSENSUS_LATENCY_MS_MEAN / 1000,
        "public_verifiable": "Partial (consortium members only)",
        "omission_detectable": "Partial",
        "caveat": "No public chain; verifiability limited to consortium members",
    }


# ---------------------------------------------------------------------------
# B6: Ethereum L1 cost model
# ---------------------------------------------------------------------------

def model_b6_eth_l1() -> dict:
    """
    Ethereum L1: calldata anchoring of 32-byte root.
    calldata cost: 16 gas/byte for non-zero bytes
    Root = 32 bytes → ~512 calldata gas
    Plus tx overhead (~21000 gas)
    Total: ~21512 gas per tx
    ETH gas price: 20-50 gwei (conservative)
    ETH price: $2500
    """
    GAS_PER_TX = 21_512
    GAS_PRICE_GWEI_MEAN = 30.0
    ETH_PRICE_USD = 2500.0

    fee_eth = GAS_PER_TX * GAS_PRICE_GWEI_MEAN * 1e-9
    fee_usd = fee_eth * ETH_PRICE_USD

    # Batched: one anchor per N events
    BATCH_SIZE_ETH = 1681
    batches_per_day = DAILY_VOLUME / BATCH_SIZE_ETH
    monthly_cost_usd = batches_per_day * 30 * fee_usd
    cost_per_1k_usd = (1000 / BATCH_SIZE_ETH) * fee_usd

    return {
        "baseline": "B6 Ethereum L1",
        "model_type": "model-only",
        "gas_per_tx": GAS_PER_TX,
        "gas_price_gwei": GAS_PRICE_GWEI_MEAN,
        "eth_price_usd": ETH_PRICE_USD,
        "fee_per_anchor_eth": round(fee_eth, 8),
        "fee_per_anchor_usd": round(fee_usd, 4),
        "monthly_cost_usd_estimate": round(monthly_cost_usd, 4),
        "cost_per_1k_events_usd": round(cost_per_1k_usd, 6),
        "tef_s_estimate": "~15s (next block)",
        "public_verifiable": True,
        "omission_detectable": "Partial",
        "caveat": "High gas price volatility; L2 would reduce cost ~100x",
    }


# ---------------------------------------------------------------------------
# B7: EVM L2 / Algorand model
# ---------------------------------------------------------------------------

def model_b7_l2_algorand() -> dict:
    """
    EVM L2 (e.g., Arbitrum): ~0.01 USD per anchor at peak
    Algorand: ~0.001 ADA equivalent ($0.0004) per tx
    """
    # Arbitrum L2
    FEE_L2_USD = 0.01
    BATCH_SIZE = 1681
    batches_per_day = DAILY_VOLUME / BATCH_SIZE
    monthly_cost_l2 = batches_per_day * 30 * FEE_L2_USD
    cost_1k_l2 = (1000 / BATCH_SIZE) * FEE_L2_USD

    # Algorand
    ALGO_FEE_ALGO = 0.001
    ALGO_PRICE_USD = 0.15
    fee_algo_usd = ALGO_FEE_ALGO * ALGO_PRICE_USD
    monthly_cost_algo = batches_per_day * 30 * fee_algo_usd
    cost_1k_algo = (1000 / BATCH_SIZE) * fee_algo_usd

    return {
        "baseline": "B7 EVM L2 / Algorand",
        "model_type": "model-only",
        "evm_l2_fee_per_anchor_usd": FEE_L2_USD,
        "evm_l2_monthly_cost_usd": round(monthly_cost_l2, 4),
        "evm_l2_cost_per_1k_usd": round(cost_1k_l2, 6),
        "algorand_fee_per_anchor_usd": round(fee_algo_usd, 6),
        "algorand_monthly_cost_usd": round(monthly_cost_algo, 4),
        "algorand_cost_per_1k_usd": round(cost_1k_algo, 6),
        "public_verifiable": True,
        "omission_detectable": "Partial",
        "tef_s_estimate": "2-5s (L2 batch) / 4s (Algorand block)",
        "caveat": "Model-based; not deployed in a live pilot",
    }


def run_e6() -> dict:
    print("=" * 60)
    print("E6: Model-Based Baselines")
    print("=" * 60)

    b4 = model_b4_ots()
    b5 = model_b5_cometbft()
    b6 = model_b6_eth_l1()
    b7 = model_b7_l2_algorand()

    summary_rows = [
        {
            "baseline": "B4 OTS-style",
            "estimated_monthly_cost_usd": b4["monthly_cost_usd_estimate"],
            "public_verifiable": b4["public_verifiable"],
            "omission_detectable": b4["omission_detectable"],
            "tef_estimate": b4["tef_s_estimate"],
            "model_only": True,
        },
        {
            "baseline": "B5 CometBFT",
            "estimated_monthly_cost_usd": b5["monthly_infra_cost_usd"],
            "public_verifiable": b5["public_verifiable"],
            "omission_detectable": b5["omission_detectable"],
            "tef_estimate": f"{b5['tef_s_estimate']}s",
            "model_only": True,
        },
        {
            "baseline": "B6 Ethereum L1",
            "estimated_monthly_cost_usd": b6["monthly_cost_usd_estimate"],
            "public_verifiable": b6["public_verifiable"],
            "omission_detectable": b6["omission_detectable"],
            "tef_estimate": b6["tef_s_estimate"],
            "model_only": True,
        },
        {
            "baseline": "B7 EVM L2/Algorand",
            "estimated_monthly_cost_usd": f"{b7['evm_l2_monthly_cost_usd']}/{b7['algorand_monthly_cost_usd']}",
            "public_verifiable": b7["public_verifiable"],
            "omission_detectable": b7["omission_detectable"],
            "tef_estimate": b7["tef_s_estimate"],
            "model_only": True,
        },
    ]

    csv_path = RESULTS_DIR / "e6_model.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows)

    import json
    detail_path = RESULTS_DIR / "e6_model_detail.json"
    with open(detail_path, "w") as f:
        json.dump({"B4": b4, "B5": b5, "B6": b6, "B7": b7}, f, indent=2)

    print(f"[E6] Results written to {csv_path}")
    for r in summary_rows:
        print(f"  {r['baseline']:20s}: ${r['estimated_monthly_cost_usd']}/mo  "
              f"public={r['public_verifiable']}")

    return {"B4": b4, "B5": b5, "B6": b6, "B7": b7}


if __name__ == "__main__":
    run_e6()
