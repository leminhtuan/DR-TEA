"""
DR-TEA — Secondary-Domain Transferability Workload Generator (W2)
=================================================================
50,000 events representing university fee collection or utility bill payment.
Tests domain transferability without redesigning the canonical evidence core.

Schema extensions over W1:
  - domain: "UNIVERSITY" | "UTILITY"
  - domain_ext: {semester, faculty_code, meter_id, bill_period, ...}

Output: w2_secondary_events.jsonl
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

SEED = 42
N_EVENTS = 50_000
OUTPUT_DIR = ROOT / "benchmark" / "data"

CHANNELS = ["BANK_TRANSFER", "MOMO_WALLET", "CARD", "ZALO_PAY", "VNPAY"]
CHANNEL_WEIGHTS = [0.45, 0.20, 0.18, 0.10, 0.07]
STATUSES = ["PAID", "PENDING", "PARTIAL", "FAILED", "REFUNDED"]
STATUS_WEIGHTS = [0.75, 0.10, 0.07, 0.05, 0.03]

SIM_START = datetime(2023, 9, 1, tzinfo=timezone.utc)
SIM_DAYS = 300

N_UNIVERSITIES = 10
FACULTIES = ["ENGINEERING", "BUSINESS", "SCIENCE", "ARTS", "MEDICINE"]
SEMESTERS = ["2023-2024-SEM1", "2023-2024-SEM2"]
BILL_PERIODS = ["2023-Q3", "2023-Q4", "2024-Q1", "2024-Q2"]


def _sample_ts(rng: random.Random) -> str:
    # University pattern: peaks at end-of-semester registration (Oct, Mar)
    day = rng.randint(0, SIM_DAYS - 1)
    dt = SIM_START + timedelta(days=day)
    # Boost October and March
    boost = 2.0 if dt.month in (10, 3) else 1.0
    if rng.random() > 1.0 / boost:
        day = rng.randint(0, SIM_DAYS - 1)
        dt = SIM_START + timedelta(days=day)
    hour = rng.choices(range(24), weights=[max(0.01, 0.12 - abs(h - 10) * 0.01) for h in range(24)])[0]
    return dt.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_university_event(rng: random.Random, inv_seq: int) -> dict:
    uni_id = rng.randint(1, N_UNIVERSITIES)
    student_id = rng.randint(1, 5000)
    faculty = rng.choice(FACULTIES)
    semester = rng.choice(SEMESTERS)
    amount = str(rng.randint(5_000_000, 25_000_000))
    status = rng.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
    if status == "PARTIAL":
        amount = str(int(int(amount) * rng.uniform(0.2, 0.8)))
    return {
        "inv_id": f"UNI{uni_id:02d}-STU{student_id:05d}-{inv_seq:06d}",
        "payer_ref": f"STU-{uni_id:02d}-{student_id:05d}",
        "amount": amount,
        "currency": "VND",
        "status": status,
        "channel": rng.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0],
        "ts": _sample_ts(rng),
        "domain": "UNIVERSITY",
        "domain_ext": {
            "semester": semester,
            "faculty_code": faculty,
            "university_id": f"UNI{uni_id:02d}",
        },
    }


def _make_utility_event(rng: random.Random, inv_seq: int) -> dict:
    meter_id = f"MTR-{rng.randint(1, 50000):06d}"
    bill_period = rng.choice(BILL_PERIODS)
    amount = str(rng.randint(50_000, 2_000_000))
    status = rng.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
    return {
        "inv_id": f"UTL-{meter_id}-{bill_period}-{inv_seq:06d}",
        "payer_ref": f"CUST-{rng.randint(1, 100000):06d}",
        "amount": amount,
        "currency": "VND",
        "status": status,
        "channel": rng.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0],
        "ts": _sample_ts(rng),
        "domain": "UTILITY",
        "domain_ext": {
            "meter_id": meter_id,
            "bill_period": bill_period,
            "utility_type": rng.choice(["ELECTRICITY", "WATER", "GAS"]),
        },
    }


def generate_secondary_workload(
    n_events: int = N_EVENTS,
    seed: int = SEED,
    output_dir: Optional[Path] = None,
) -> tuple[list[dict], dict]:
    rng = random.Random(seed + 1)  # different seed from W1
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []
    # 60% university, 40% utility
    n_uni = int(n_events * 0.6)
    n_util = n_events - n_uni

    for i in range(n_uni):
        events.append(_make_university_event(rng, i))
    for i in range(n_util):
        events.append(_make_utility_event(rng, i))

    rng.shuffle(events)

    schema_changes = {
        "added_fields": ["domain_ext.semester", "domain_ext.faculty_code",
                         "domain_ext.university_id", "domain_ext.meter_id",
                         "domain_ext.bill_period", "domain_ext.utility_type"],
        "core_fields_unchanged": ["inv_id", "payer_ref", "amount", "currency", "status", "channel", "ts"],
        "n_added_fields_university": 3,
        "n_added_fields_utility": 3,
    }

    stats = {
        "seed": seed + 1,
        "n_university_events": n_uni,
        "n_utility_events": n_util,
        "total_events": len(events),
        "schema_changes": schema_changes,
    }

    out_path = output_dir / "w2_secondary_events.jsonl"
    stats_path = output_dir / "w2_secondary_stats.json"

    with open(out_path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"[W2] Generated {len(events)} events → {out_path}")
    return events, stats


if __name__ == "__main__":
    generate_secondary_workload()
