"""
DR-TEA — E8: ADA Price Uncertainty Monte Carlo
================================================
Uses historical ADA/USD prices from ada-usd-max.csv (3216 daily observations).
Fits a log-normal distribution to daily log-returns for price simulation.

Scenarios:
  - Batch sizes: 500, 1681, 5000
  - Daily volumes: 1000, 5000, 10000, 20000, 50000
  - 10,000 Monte Carlo samples

Reports P50, P95, P99 monthly cost in USD.

Outputs: results/e8_montecarlo.csv
         figures/fig5_montecarlo_cost.pdf (via analyze.py)
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import lognorm

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from services.anchoring.dry_run_adapter import (
    estimate_fee_ada, DRY_RUN_TX_SIZE_BYTES_MEAN,
    MIN_FEE_A, MIN_FEE_B, LOVELACE_PER_ADA,
)

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SEED = 42
N_MC_SAMPLES = 10_000
BATCH_SIZES = [500, 1681, 5000]
DAILY_VOLUMES = [1_000, 5_000, 10_000, 20_000, 50_000]
DAYS_PER_MONTH = 30

# ADA price data path — the file sits alongside the .tex manuscript
ADA_CSV_CANDIDATES = [
    Path("/Users/leminhtuan0810/Desktop/DR-TEA/ada-usd-max.csv"),
    ROOT.parent / "ada-usd-max.csv",
    ROOT / "ada-usd-max.csv",
]


def load_ada_prices() -> np.ndarray:
    """Load historical ADA/USD daily close prices."""
    for candidate in ADA_CSV_CANDIDATES:
        if candidate.exists():
            try:
                # User's file uses semicolon separator and European decimal commas
                df = pd.read_csv(candidate, sep=";", decimal=",", encoding="utf-8-sig")
                prices = df["close_price_usd"].dropna().values.astype(float)
                prices = prices[prices > 0]
                print(f"  [E8] Loaded {len(prices)} ADA price observations from {candidate}")
                return prices
            except Exception as e:
                print(f"  [E8] Failed to load {candidate}: {e}")

    # Fallback: synthesize from known ADA stats (2017-2024)
    print("  [E8] WARNING: ada-usd-max.csv not found. Using synthetic price distribution.")
    rng = np.random.default_rng(SEED)
    mu = -0.001
    sigma = 0.06
    n = 2000
    log_returns = rng.normal(mu, sigma, n)
    prices = np.exp(np.cumsum(log_returns)) * 0.10
    return prices


def fit_price_model(prices: np.ndarray, rng_seed: int = SEED) -> tuple[np.ndarray, float, float]:
    """
    Fit log-normal distribution to ADA prices and return MC samples.

    Strategy:
    1. Compute daily log returns from historical prices
    2. Fit normal distribution to log returns
    3. Bootstrap sample future price paths from recent prices
    """
    # Only use recent 2 years (more relevant for forecasting)
    recent_prices = prices[-730:] if len(prices) >= 730 else prices
    log_returns = np.diff(np.log(recent_prices))
    mu_log = float(np.mean(log_returns))
    sigma_log = float(np.std(log_returns))

    # Simulate future monthly average price
    # Use a simple bootstrapped approach: sample N monthly averages from
    # rolling 30-day windows in the historical data
    np_rng = np.random.default_rng(rng_seed)

    # Bootstrap from daily price distribution (simpler, more conservative)
    sampled_prices = np_rng.choice(recent_prices, size=N_MC_SAMPLES, replace=True)

    # Add noise from fitted log-normal
    log_perturbation = np_rng.normal(mu_log * 30, sigma_log * np.sqrt(30), N_MC_SAMPLES)
    simulated_prices = sampled_prices * np.exp(log_perturbation)
    simulated_prices = np.clip(simulated_prices, 0.001, 10.0)  # safety bounds

    return simulated_prices, mu_log, sigma_log


def run_scenario(
    batch_size: int,
    daily_volume: int,
    price_samples: np.ndarray,
    rng: np.random.Generator,
) -> dict:
    """Run Monte Carlo for one (batch_size, daily_volume) scenario."""
    # Fee per batch in ADA (sample from tx_size distribution)
    tx_size_samples = rng.normal(DRY_RUN_TX_SIZE_BYTES_MEAN, 20.0, N_MC_SAMPLES).astype(int)
    tx_size_samples = np.clip(tx_size_samples, 280, 600)
    fee_lovelace_samples = MIN_FEE_A * tx_size_samples + MIN_FEE_B
    fee_ada_samples = fee_lovelace_samples / LOVELACE_PER_ADA

    # Batches per month
    batches_per_day = np.ceil(daily_volume / batch_size)
    batches_per_month = batches_per_day * DAYS_PER_MONTH

    # Monthly cost in ADA
    monthly_cost_ada = batches_per_month * fee_ada_samples

    # Monthly cost in USD
    monthly_cost_usd = monthly_cost_ada * price_samples

    p50 = float(np.percentile(monthly_cost_usd, 50))
    p95 = float(np.percentile(monthly_cost_usd, 95))
    p99 = float(np.percentile(monthly_cost_usd, 99))
    mean = float(np.mean(monthly_cost_usd))
    std = float(np.std(monthly_cost_usd))

    return {
        "batch_size": batch_size,
        "daily_volume": daily_volume,
        "batches_per_month": int(batches_per_month),
        "cost_p50_usd": round(p50, 4),
        "cost_p95_usd": round(p95, 4),
        "cost_p99_usd": round(p99, 4),
        "cost_mean_usd": round(mean, 4),
        "cost_std_usd": round(std, 4),
        "fee_ada_mean": round(float(np.mean(fee_ada_samples)), 6),
        "n_mc_samples": N_MC_SAMPLES,
    }


def run_e8() -> list[dict]:
    print("=" * 60)
    print("E8: ADA Price Uncertainty Monte Carlo")
    print("=" * 60)

    prices = load_ada_prices()
    print(f"  Price range: ${prices.min():.4f} - ${prices.max():.4f} USD")
    print(f"  Price median: ${np.median(prices):.4f} USD")

    price_samples, mu_log, sigma_log = fit_price_model(prices, SEED)
    print(f"  Log-return fit: mu={mu_log:.5f}, sigma={sigma_log:.5f}")
    print(f"  MC price samples: P50=${np.percentile(price_samples, 50):.4f} "
          f"P95=${np.percentile(price_samples, 95):.4f}")

    rng = np.random.default_rng(SEED)
    rows: list[dict] = []

    for bs in BATCH_SIZES:
        for dv in DAILY_VOLUMES:
            print(f"  batch={bs:5d} daily_vol={dv:6d}: ", end="", flush=True)
            row = run_scenario(bs, dv, price_samples, rng)
            rows.append(row)
            print(f"P50=${row['cost_p50_usd']:.4f} P95=${row['cost_p95_usd']:.4f} P99=${row['cost_p99_usd']:.4f}")

    csv_path = RESULTS_DIR / "e8_montecarlo.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    # Also save price model params for figure
    import json
    model_path = RESULTS_DIR / "e8_price_model.json"
    with open(model_path, "w") as f:
        json.dump({
            "n_historical_prices": int(len(prices)),
            "price_min_usd": round(float(prices.min()), 6),
            "price_max_usd": round(float(prices.max()), 6),
            "price_median_usd": round(float(np.median(prices)), 6),
            "log_return_mu": round(mu_log, 6),
            "log_return_sigma": round(sigma_log, 6),
            "mc_samples": N_MC_SAMPLES,
            "seed": SEED,
        }, f, indent=2)

    print(f"[E8] Results written to {csv_path}")

    # Save raw samples for base scenario (batch=1681, vol=5000) for figure
    bs_fig, dv_fig = 1681, 5000
    rng2 = np.random.default_rng(SEED)
    tx_sizes = rng2.normal(DRY_RUN_TX_SIZE_BYTES_MEAN, 20.0, N_MC_SAMPLES).clip(280, 600).astype(int)
    fees_ada = (MIN_FEE_A * tx_sizes + MIN_FEE_B) / LOVELACE_PER_ADA
    bpm = np.ceil(dv_fig / bs_fig) * DAYS_PER_MONTH
    raw_costs = bpm * fees_ada * price_samples

    raw_path = RESULTS_DIR / "e8_raw_samples.npy"
    np.save(raw_path, raw_costs)
    print(f"     Raw samples saved to {raw_path}")

    return rows


if __name__ == "__main__":
    run_e8()
