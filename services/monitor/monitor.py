"""
DR-TEA — Omission Monitor and Fault Injector
=============================================
Implements Algorithm 1 (lines 12-18): monitor loop, SLA checking, dispute generation.

Monitor checks:
  FOR each monitor independently:
    IF receipt older than Δ has no proof → generate dispute D(e, R_SSC, R_school)
"""

from __future__ import annotations

import time
import random
import json
from dataclasses import dataclass, asdict
from threading import Lock
from typing import Optional

from services.receipts.receipt_service import Receipt


# ---------------------------------------------------------------------------
# Dispute record
# ---------------------------------------------------------------------------

@dataclass
class Dispute:
    """D(e, R_SSC, R_school) — evidence of omission."""
    inv_id: str
    event_hash_hex: str
    ssc_receipt_seq: int
    ssc_receipt_ts: float
    sla_window_s: float
    detected_at: float
    monitor_id: str
    has_school_receipt: bool
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def mttd(self) -> float:
        """Mean Time To Detect = detected_at - ssc_receipt_ts"""
        return self.detected_at - self.ssc_receipt_ts


# ---------------------------------------------------------------------------
# Anchor record (simulated or real)
# ---------------------------------------------------------------------------

@dataclass
class AnchorRecord:
    batch_id: int
    tx_id: str
    root_hex: str
    confirmed_at: float   # Unix time of confirmed anchoring
    event_hash_hexes: list[str]  # event hashes included in this batch


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class OmissionMonitor:
    """
    Monitors receipt log and anchor records.
    Raises disputes for receipts older than SLA window with no confirmed anchor.

    Corresponds to Algorithm 1, FOR loop (lines 12-18).
    """

    def __init__(
        self,
        monitor_id: str,
        sla_window_s: float = 300.0,  # default 5-minute SLA
    ) -> None:
        self._monitor_id = monitor_id
        self._sla_window_s = sla_window_s
        self._disputes: list[Dispute] = []
        self._lock = Lock()
        self._heartbeat_ts: float = time.time()

    @property
    def sla_window_s(self) -> float:
        return self._sla_window_s

    def run_check(
        self,
        receipts: list[Receipt],
        anchor_records: list[AnchorRecord],
        current_time: Optional[float] = None,
    ) -> list[Dispute]:
        """
        Run one monitoring sweep.

        Returns list of new disputes raised in this sweep.
        """
        now = current_time if current_time is not None else time.time()

        # Build set of anchored event hashes
        anchored_hashes: set[str] = set()
        for ar in anchor_records:
            for h in ar.event_hash_hexes:
                anchored_hashes.add(h)

        new_disputes: list[Dispute] = []

        for receipt in receipts:
            age = now - receipt.ts_issued
            if age < self._sla_window_s:
                # Receipt is still within SLA window — not yet overdue
                continue

            if receipt.event_hash_hex in anchored_hashes:
                # Anchored in time — no dispute
                continue

            # Overdue and not anchored → raise dispute
            dispute = Dispute(
                inv_id=receipt.inv_id,
                event_hash_hex=receipt.event_hash_hex,
                ssc_receipt_seq=receipt.seq,
                ssc_receipt_ts=receipt.ts_issued,
                sla_window_s=self._sla_window_s,
                detected_at=now,
                monitor_id=self._monitor_id,
                has_school_receipt=not receipt.provisional_no_cosign,
                notes="SLA_EXCEEDED_NO_ANCHOR",
            )
            new_disputes.append(dispute)

        with self._lock:
            self._disputes.extend(new_disputes)

        self._heartbeat_ts = now
        return new_disputes

    def get_disputes(self) -> list[Dispute]:
        with self._lock:
            return list(self._disputes)

    def reset(self) -> None:
        with self._lock:
            self._disputes.clear()


# ---------------------------------------------------------------------------
# Omission Metrics Calculator
# ---------------------------------------------------------------------------

@dataclass
class OmissionMetrics:
    tp: int = 0   # True Positive: actually omitted, detected
    fp: int = 0   # False Positive: not omitted, but flagged
    fn: int = 0   # False Negative: omitted, not detected
    tn: int = 0   # True Negative: not omitted, not flagged

    @property
    def odr(self) -> float:
        """Omission Detection Rate = Recall = TP / (TP + FN)"""
        denom = self.tp + self.fn
        return self.tp / denom if denom > 0 else 0.0

    @property
    def fpr(self) -> float:
        """False Positive Rate = FP / (FP + TN)"""
        denom = self.fp + self.tn
        return self.fp / denom if denom > 0 else 0.0

    @property
    def precision(self) -> float:
        """Precision = TP / (TP + FP)"""
        denom = self.tp + self.fp
        return self.tp / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        return self.odr

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
            "odr": self.odr, "fpr": self.fpr,
            "precision": self.precision, "recall": self.recall, "f1": self.f1,
        }


def compute_omission_metrics(
    omitted_hashes: set[str],
    disputed_hashes: set[str],
    all_hashes: set[str],
) -> OmissionMetrics:
    """
    Compute TP/FP/FN/TN for omission detection.

    omitted_hashes: ground-truth set of events that were selectively omitted
    disputed_hashes: set of events flagged by the monitor
    all_hashes: complete set of event hashes in the experiment
    """
    m = OmissionMetrics()
    for h in all_hashes:
        actually_omitted = h in omitted_hashes
        flagged = h in disputed_hashes
        if actually_omitted and flagged:
            m.tp += 1
        elif not actually_omitted and flagged:
            m.fp += 1
        elif actually_omitted and not flagged:
            m.fn += 1
        else:
            m.tn += 1
    return m


# ---------------------------------------------------------------------------
# Fault Injector
# ---------------------------------------------------------------------------

class FaultInjector:
    """
    Simulates selective omission attacks after receipt creation.

    In dry-run mode:
    - Events receive receipts (visible to monitor).
    - A subset of events are excluded from batching (selective omission).
    - The monitor then flags these as disputes.
    """

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._omission_log: list[dict] = []

    def inject_omissions(
        self,
        event_hash_hexes: list[str],
        omission_rate: float,
    ) -> tuple[list[str], set[str]]:
        """
        Given all event hashes, randomly omit a fraction.

        Returns:
            (included_hashes, omitted_hashes_set)
        where included_hashes go to batching and omitted_hashes are withheld.
        """
        omitted: set[str] = set()
        included: list[str] = []

        for h in event_hash_hexes:
            if self._rng.random() < omission_rate:
                omitted.add(h)
                self._omission_log.append({
                    "event_hash_hex": h,
                    "action": "OMITTED",
                    "ts": time.time(),
                })
            else:
                included.append(h)

        return included, omitted

    def inject_malformed(
        self,
        raw_events: list[dict],
        malformed_rate: float,
        fault_types: Optional[list[str]] = None,
    ) -> tuple[list[dict], list[dict], list[str]]:
        """
        Inject syntactic faults into a fraction of events.

        Returns:
            (normal_events, faulted_events, fault_descriptions)
        """
        if fault_types is None:
            fault_types = [
                "MISSING_INV_ID",
                "NEGATIVE_AMOUNT",
                "FUTURE_TS",
                "OVERSIZED_PAYLOAD",
                "INVALID_STATUS",
                "MISSING_CURRENCY",
                "NON_NUMERIC_AMOUNT",
            ]

        normal: list[dict] = []
        faulted: list[dict] = []
        descriptions: list[str] = []

        for ev in raw_events:
            if self._rng.random() < malformed_rate:
                fault_type = self._rng.choice(fault_types)
                broken = dict(ev)  # shallow copy
                if fault_type == "MISSING_INV_ID":
                    broken.pop("inv_id", None)
                elif fault_type == "NEGATIVE_AMOUNT":
                    broken["amount"] = "-100.00"
                elif fault_type == "FUTURE_TS":
                    broken["ts"] = "2099-01-01T00:00:00Z"
                elif fault_type == "OVERSIZED_PAYLOAD":
                    broken["inv_id"] = "X" * 100_000
                elif fault_type == "INVALID_STATUS":
                    broken["status"] = "INVALID_STATUS_CODE"
                elif fault_type == "MISSING_CURRENCY":
                    broken.pop("currency", None)
                elif fault_type == "NON_NUMERIC_AMOUNT":
                    broken["amount"] = "not-a-number"
                faulted.append(broken)
                descriptions.append(fault_type)
            else:
                normal.append(ev)

        return normal, faulted, descriptions

    def get_omission_log(self) -> list[dict]:
        return list(self._omission_log)

    def reset(self) -> None:
        self._omission_log.clear()
