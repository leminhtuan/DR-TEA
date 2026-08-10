"""
DR-TEA — K-12 SSC Workload Generator (W1)
==========================================
Generates 100,000 synthetic K-12 payment events calibrated to SSC patterns.

Features:
  - Diurnal peaks (morning 8-10am, afternoon 2-4pm)
  - September enrollment burst (+3x volume)
  - Duplicates (~3%)
  - Malformed payload rate (configurable)
  - Refunds, partial payments, late callbacks
  - Fixed seed=42 for reproducibility

Output: events.jsonl, stats.json
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Ensure project root is on path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


SEED = 42
N_EVENTS = 100_000
OUTPUT_DIR = ROOT / "benchmark" / "data"

# Simulation period: one academic year (Sep 2023 – Jun 2024)
SIM_START = datetime(2023, 9, 1, tzinfo=timezone.utc)
SIM_END = datetime(2024, 6, 30, tzinfo=timezone.utc)
SIM_DAYS = (SIM_END - SIM_START).days

CHANNELS = ["BANK_TRANSFER", "MOMO_WALLET", "ZALO_PAY", "CARD", "CASH_DEPOSIT"]
CHANNEL_WEIGHTS = [0.40, 0.25, 0.20, 0.10, 0.05]

STATUSES = ["PAID", "PENDING", "REFUNDED", "PARTIAL", "FAILED", "LATE"]
STATUS_WEIGHTS = [0.72, 0.10, 0.05, 0.06, 0.04, 0.03]

# 50 synthetic schools
N_SCHOOLS = 50
N_STUDENTS_PER_SCHOOL = 400

# Fee range (Vietnamese Dong, in thousands)
TUITION_MIN_VND = 1_500_000
TUITION_MAX_VND = 8_000_000


def _diurnal_weight(hour: int) -> float:
    """
    Diurnal payment probability weight.
    Peaks at 9am (0.20) and 3pm (0.15); low overnight.
    """
    if 8 <= hour <= 10:
        return 0.20
    elif 14 <= hour <= 16:
        return 0.15
    elif 11 <= hour <= 13:
        return 0.10
    elif 17 <= hour <= 20:
        return 0.08
    elif 6 <= hour <= 7:
        return 0.04
    else:
        return 0.01


def _month_weight(month: int) -> float:
    """September burst (enrollment), moderate Jan/Feb (semester 2)."""
    weights = {
        9: 3.0, 10: 1.2, 11: 1.0, 12: 0.9,
        1: 1.8, 2: 1.5, 3: 1.0, 4: 0.9, 5: 0.8, 6: 0.7,
    }
    return weights.get(month, 1.0)


def _sample_timestamp(rng: random.Random) -> str:
    """Sample a plausible payment timestamp within the simulation period."""
    # Sample a day within the period
    day_offset = rng.randint(0, SIM_DAYS - 1)
    dt = SIM_START + timedelta(days=day_offset)

    # Weight by month
    month_w = _month_weight(dt.month)
    if rng.random() > month_w / 3.0:
        # resample day if not in a high-traffic month (approximate thinning)
        day_offset = rng.randint(0, SIM_DAYS - 1)
        dt = SIM_START + timedelta(days=day_offset)

    # Sample hour by diurnal distribution
    hours = list(range(24))
    weights = [_diurnal_weight(h) for h in hours]
    total = sum(weights)
    weights = [w / total for w in weights]
    hour = rng.choices(hours, weights=weights, k=1)[0]
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    dt = dt.replace(hour=hour, minute=minute, second=second)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_event(
    rng: random.Random,
    school_id: int,
    student_id: int,
    inv_seq: int,
    status: Optional[str] = None,
) -> dict:
    """Generate one canonical payment event dict."""
    ts = _sample_timestamp(rng)
    amount_vnd = rng.randint(TUITION_MIN_VND // 1000, TUITION_MAX_VND // 1000) * 1000
    chosen_status = status or rng.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
    channel = rng.choices(CHANNELS, weights=CHANNEL_WEIGHTS, k=1)[0]

    if chosen_status == "PARTIAL":
        amount_vnd = int(amount_vnd * rng.uniform(0.1, 0.9))

    inv_id = f"INV-SCH{school_id:03d}-STU{student_id:05d}-{inv_seq:06d}"
    payer_ref = f"PAR-{school_id:03d}-{student_id:05d}"

    return {
        "inv_id": inv_id,
        "payer_ref": payer_ref,
        "amount": str(amount_vnd),
        "currency": "VND",
        "status": chosen_status,
        "channel": channel,
        "ts": ts,
        "domain": "K12",
    }


def generate_k12_workload(
    n_events: int = N_EVENTS,
    seed: int = SEED,
    duplicate_rate: float = 0.03,
    late_callback_rate: float = 0.02,
    output_dir: Optional[Path] = None,
) -> tuple[list[dict], dict]:
    """
    Generate K-12 workload.

    Returns:
        (events, stats) where events is a list of raw event dicts
    """
    rng = random.Random(seed)
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []
    school_ids = list(range(1, N_SCHOOLS + 1))
    inv_seq = 1

    # Generate base events
    for _ in range(n_events):
        school_id = rng.choice(school_ids)
        student_id = rng.randint(1, N_STUDENTS_PER_SCHOOL)
        ev = _make_event(rng, school_id, student_id, inv_seq)
        inv_seq += 1
        events.append(ev)

    # Inject duplicates (exact copies with same inv_id → will be caught by idempotency)
    n_dupes = int(n_events * duplicate_rate)
    for _ in range(n_dupes):
        orig = rng.choice(events[:n_events])
        events.append(dict(orig))  # exact duplicate

    # Inject late callbacks (valid events with PAID status replacing PENDING)
    n_late = int(n_events * late_callback_rate)
    for _ in range(n_late):
        orig = rng.choice([e for e in events if e["status"] == "PENDING"])
        late = dict(orig)
        late["status"] = "LATE"
        events.append(late)

    # Shuffle
    rng.shuffle(events)

    stats = {
        "seed": seed,
        "n_base_events": n_events,
        "n_duplicates_injected": n_dupes,
        "n_late_callbacks": n_late,
        "total_events": len(events),
        "status_counts": {s: sum(1 for e in events if e["status"] == s) for s in STATUSES},
        "channel_counts": {c: sum(1 for e in events if e["channel"] == c) for c in CHANNELS},
    }

    # Write outputs
    events_path = output_dir / "w1_k12_events.jsonl"
    stats_path = output_dir / "w1_k12_stats.json"

    with open(events_path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"[W1] Generated {len(events)} events → {events_path}")
    print(f"     Stats: {n_dupes} duplicates, {n_late} late callbacks")

    return events, stats


if __name__ == "__main__":
    generate_k12_workload()
