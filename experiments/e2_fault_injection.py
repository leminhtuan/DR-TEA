"""
DR-TEA — E2: Fault Injection
==============================
Malformed rates: 0%, 5%, 15.7%, 30%
Metrics: FIR_syn (syntactic fault isolation rate), FRR (false rejection rate)
30 simulation runs per malformed rate.

Outputs: results/e2_fault.csv
"""

from __future__ import annotations

import csv
import random
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import bootstrap

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from services.ingestion.canonicalizer import IngestionGateway
from services.monitor.monitor import FaultInjector

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SEED = 42
N_RUNS = 30
MALFORMED_RATES = [0.0, 0.05, 0.157, 0.30]
N_EVENTS_PER_RUN = 1000

VALID_EVENT_TEMPLATE = {
    "inv_id": "INV-{i:06d}",
    "payer_ref": "PAR-{i:06d}",
    "amount": "1500000",
    "currency": "VND",
    "status": "PAID",
    "channel": "BANK_TRANSFER",
    "ts": "2024-01-15T09:30:00Z",
}

MALFORMED_VARIANTS = [
    # (field_to_break, new_value, or remove field)
    {"_break": "missing_inv_id"},
    {"_break": "negative_amount"},
    {"_break": "invalid_status"},
    {"_break": "non_numeric_amount"},
    {"_break": "missing_currency"},
]


def make_valid(i: int) -> dict:
    return {k: v.format(i=i) if isinstance(v, str) else v
            for k, v in VALID_EVENT_TEMPLATE.items()}


def make_malformed(rng: random.Random, i: int) -> dict:
    variant = rng.choice(MALFORMED_VARIANTS)
    base = make_valid(i + 999_000)  # ensure different inv_id
    kind = variant["_break"]
    ev = dict(base)
    if kind == "missing_inv_id":
        ev.pop("inv_id")
    elif kind == "negative_amount":
        ev["amount"] = "-100"
    elif kind == "invalid_status":
        ev["status"] = "COMPLETELY_INVALID"
    elif kind == "non_numeric_amount":
        ev["amount"] = "not-a-number"
    elif kind == "missing_currency":
        ev.pop("currency")
    return ev


def run_single(malformed_rate: float, run_id: int, rng: random.Random) -> dict:
    gw = IngestionGateway()
    n_valid = int(N_EVENTS_PER_RUN * (1 - malformed_rate))
    n_malformed = N_EVENTS_PER_RUN - n_valid

    # Generate events
    events = []
    labels = []  # "valid" or "malformed"

    for i in range(n_valid):
        events.append(make_valid(run_id * N_EVENTS_PER_RUN + i))
        labels.append("valid")
    for i in range(n_malformed):
        events.append(make_malformed(rng, run_id * N_EVENTS_PER_RUN + i))
        labels.append("malformed")

    # Shuffle together
    combined = list(zip(events, labels))
    rng.shuffle(combined)

    n_injected = n_malformed
    n_blocked = 0
    n_valid_rejected = 0
    n_valid_total = 0

    for ev, label in combined:
        result = gw.ingest(ev)
        if label == "malformed":
            if not result.accepted:
                n_blocked += 1
        else:
            n_valid_total += 1
            if not result.accepted and result.reason != "DUPLICATE_IDEM_KEY":
                n_valid_rejected += 1

    fir_syn = n_blocked / n_injected if n_injected > 0 else 1.0
    frr = n_valid_rejected / n_valid_total if n_valid_total > 0 else 0.0

    return {
        "malformed_rate": malformed_rate,
        "run_id": run_id,
        "n_total": N_EVENTS_PER_RUN,
        "n_injected": n_injected,
        "n_blocked": n_blocked,
        "fir_syn": round(fir_syn, 6),
        "frr": round(frr, 6),
    }


def run_e2() -> list[dict]:
    print("=" * 60)
    print("E2: Fault Injection")
    print("=" * 60)

    rng = random.Random(SEED)
    raw_rows: list[dict] = []

    for rate in MALFORMED_RATES:
        print(f"  malformed_rate={rate:.1%}: ", end="", flush=True)
        for run in range(N_RUNS):
            row = run_single(rate, run, rng)
            raw_rows.append(row)
        print(f"{N_RUNS} runs")

    # Summarize by malformed_rate
    summary = []
    for rate in MALFORMED_RATES:
        subset = [r for r in raw_rows if r["malformed_rate"] == rate]
        fir_vals = np.array([r["fir_syn"] for r in subset])
        frr_vals = np.array([r["frr"] for r in subset])

        def ci(arr: np.ndarray) -> tuple[float, float]:
            if arr.std() < 1e-10:
                return float(arr[0]), float(arr[0])
            res = bootstrap((arr,), np.mean, n_resamples=1000,
                            confidence_level=0.95, random_state=SEED, method="percentile")
            return float(res.confidence_interval.low), float(res.confidence_interval.high)

        fir_lo, fir_hi = ci(fir_vals)
        frr_lo, frr_hi = ci(frr_vals)

        injected_mean = int(np.mean([r["n_injected"] for r in subset]))
        blocked_mean = int(np.mean([r["n_blocked"] for r in subset]))

        summary.append({
            "malformed_rate_pct": f"{rate * 100:.1f}%",
            "n_injected_mean": injected_mean,
            "n_blocked_mean": blocked_mean,
            "fir_syn_mean": round(float(np.mean(fir_vals)), 6),
            "fir_syn_ci_lo": round(fir_lo, 6),
            "fir_syn_ci_hi": round(fir_hi, 6),
            "frr_mean": round(float(np.mean(frr_vals)), 6),
            "frr_ci_lo": round(frr_lo, 6),
            "frr_ci_hi": round(frr_hi, 6),
        })

    csv_path = RESULTS_DIR / "e2_fault.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary[0].keys())
        writer.writeheader()
        writer.writerows(summary)

    print(f"[E2] Results written to {csv_path}")
    for row in summary:
        print(f"  rate={row['malformed_rate_pct']:6s}: "
              f"FIR_syn={row['fir_syn_mean']:.4f} [{row['fir_syn_ci_lo']:.4f},{row['fir_syn_ci_hi']:.4f}] "
              f"FRR={row['frr_mean']:.4f}")
    return summary


if __name__ == "__main__":
    run_e2()
