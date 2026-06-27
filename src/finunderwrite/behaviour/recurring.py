"""Recurring-transaction detection.

Groups transactions by normalized merchant + amount band, infers cadence from
date-difference clustering, and classifies each recurring group. Pure
pandas/numpy; deterministic.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
from pydantic import BaseModel

from finunderwrite.contracts.transaction import CanonicalTransaction

# Cadence anchors in days and their acceptance windows.
_CADENCE_ANCHORS: list[tuple[str, float, float]] = [
    ("weekly", 7.0, 3.0),
    ("monthly", 30.0, 8.0),
    ("quarterly", 91.0, 20.0),
]

_MIN_OCCURRENCES = 3
_AMOUNT_TOLERANCE = 0.10  # relative band so small drifts still group

_RENT_KEYWORDS = ("rent", "landlord", "nobroker")
_INSURANCE_KEYWORDS = ("insurance", "premium", "lic", "policy")
_UTILITY_KEYWORDS = ("electricity", "water", "gas", "broadband", "bill", "recharge")
_SIP_KEYWORDS = ("sip", "mutual", "groww", "zerodha", "upstox", "nps")
_SUBSCRIPTION_KEYWORDS = ("netflix", "spotify", "prime", "subscription", "hotstar")
_EMI_KEYWORDS = ("emi", "installment", "instalment")
_LOAN_KEYWORDS = ("loan", "repayment", "disbursement")


class RecurringItem(BaseModel):
    """A detected recurring transaction group."""

    merchant: str
    category: str
    direction: str  # "credit" or "debit"
    cadence: str  # "weekly" | "monthly" | "quarterly"
    median_amount: float
    amount_tolerance: float
    occurrences: int
    confidence: float


def _to_float(value: Decimal | float | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _frame(transactions: list[CanonicalTransaction]) -> pd.DataFrame:
    rows = []
    for txn in transactions:
        debit = _to_float(txn.debit)
        credit = _to_float(txn.credit)
        if debit == 0 and credit == 0:
            continue
        direction = "credit" if credit > 0 else "debit"
        rows.append(
            {
                "date": pd.Timestamp(txn.date),
                "amount": credit if direction == "credit" else debit,
                "direction": direction,
                "merchant": (txn.merchant or "").strip().lower(),
                "description": (txn.description or "").lower(),
                "category": txn.category or "",
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date").reset_index(drop=True)
    return df


def detect_recurring(transactions: list[CanonicalTransaction]) -> list[RecurringItem]:
    """Detect recurring transaction groups. Returns [] on insufficient data."""
    df = _frame(transactions)
    if df.empty:
        return []

    items: list[RecurringItem] = []
    df = df.assign(_used=False)

    # Group by merchant + direction; within each, cluster by amount band.
    for (merchant, direction), group in df.groupby(["merchant", "direction"]):
        if not merchant or len(group) < _MIN_OCCURRENCES:
            continue
        for cluster in _cluster_by_amount(group):
            if len(cluster) < _MIN_OCCURRENCES:
                continue
            item = _classify_cluster(merchant, direction, cluster)
            if item is not None:
                items.append(item)

    items.sort(key=lambda it: (-it.confidence, -it.occurrences))
    return items


def _cluster_by_amount(group: pd.DataFrame) -> list[pd.DataFrame]:
    """Split a merchant/direction group into amount-band clusters."""
    ordered = group.sort_values("amount").reset_index(drop=True)
    clusters: list[list[int]] = []
    current: list[int] = []
    anchor: float | None = None

    for idx, amount in enumerate(ordered["amount"]):
        if anchor is None:
            current = [idx]
            anchor = amount
            continue
        tol = max(abs(anchor) * _AMOUNT_TOLERANCE, 1.0)
        if abs(amount - anchor) <= tol:
            current.append(idx)
            anchor = float(np.mean(ordered.loc[current, "amount"]))
        else:
            clusters.append(current)
            current = [idx]
            anchor = amount
    if current:
        clusters.append(current)

    return [ordered.loc[c] for c in clusters]


def _infer_cadence(dates: pd.Series) -> tuple[str | None, float]:
    """Return (cadence, regularity) from sorted transaction dates."""
    if len(dates) < 2:
        return None, 0.0
    ordered = dates.sort_values()
    diffs = np.diff(ordered.values).astype("timedelta64[D]").astype(float)
    diffs = diffs[diffs > 0]
    if len(diffs) == 0:
        return None, 0.0

    median_gap = float(np.median(diffs))
    best_cadence: str | None = None
    best_window = np.inf
    for name, anchor, window in _CADENCE_ANCHORS:
        if abs(median_gap - anchor) <= window and window < best_window:
            best_cadence = name
            best_window = window

    if best_cadence is None:
        return None, 0.0

    # Regularity: 1 - normalized dispersion of gaps (clamped to [0, 1]).
    regularity = 1.0 - min(float(np.std(diffs)) / median_gap, 1.0) if median_gap > 0 else 0.0
    return best_cadence, regularity


def _classify_cluster(
    merchant: str,
    direction: str,
    cluster: pd.DataFrame,
) -> RecurringItem | None:
    cadence, regularity = _infer_cadence(cluster["date"])
    if cadence is None:
        return None

    median_amount = float(cluster["amount"].median())
    occurrences = len(cluster)
    text = f"{merchant} {' '.join(cluster['description'].tolist())}"
    category = _classify_category(direction, median_amount, text, cadence)

    occurrence_conf = min(occurrences / 6.0, 1.0)
    confidence = round(0.5 * regularity + 0.5 * occurrence_conf, 4)

    return RecurringItem(
        merchant=merchant,
        category=category,
        direction=direction,
        cadence=cadence,
        median_amount=round(median_amount, 2),
        amount_tolerance=round(max(abs(median_amount) * _AMOUNT_TOLERANCE, 1.0), 2),
        occurrences=occurrences,
        confidence=confidence,
    )


def _classify_category(
    direction: str,
    amount: float,
    text: str,
    cadence: str,
) -> str:
    if direction == "credit":
        # Large recurring monthly credit = salary; otherwise a loan disbursement.
        if any(k in text for k in _LOAN_KEYWORDS):
            return "Loan Repayment"
        return "Salary"

    if any(k in text for k in _RENT_KEYWORDS):
        return "Rent"
    if any(k in text for k in _EMI_KEYWORDS):
        return "EMI"
    if any(k in text for k in _INSURANCE_KEYWORDS):
        return "Insurance"
    if any(k in text for k in _SIP_KEYWORDS):
        return "SIP"
    if any(k in text for k in _SUBSCRIPTION_KEYWORDS):
        return "Subscription"
    if any(k in text for k in _LOAN_KEYWORDS):
        return "Loan Repayment"
    if any(k in text for k in _UTILITY_KEYWORDS):
        return "Utility"

    # Fall back on cadence/amount heuristics.
    if cadence == "monthly" and amount >= 5000:
        return "Rent"
    return "Subscription"
