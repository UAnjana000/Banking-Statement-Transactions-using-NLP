"""Underwriting feature engineering.

Turns FinancialProfile + BehaviourSummary into a flat, deterministic feature
vector (one row per customer). This IS the ML feature table. Pure pandas/numpy;
no torch.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from finunderwrite.behaviour.summary import BehaviourSummary
from finunderwrite.contracts.profile import FinancialProfile

# Category buckets emitted as spend-percentage features (pct_<name>).
_CATEGORY_FEATURES = (
    "Food",
    "Groceries",
    "Shopping",
    "Healthcare",
    "Travel",
    "Entertainment",
    "Utilities",
    "Investments",
    "Rent",
    "Education",
    "Insurance",
    "Transfers",
    "Telecom",
    "Fuel",
)

_PAYMENT_FEATURES = ("UPI", "ATM", "POS", "NEFT", "IMPS")

# Documented, stable output schema (order matters for the ML table).
FEATURE_COLUMNS: tuple[str, ...] = (
    "customer_id",
    "avg_income",
    "income_consistency",
    "avg_monthly_spend",
    "avg_monthly_saving",
    "savings_rate",
    "investment_ratio",
    "emi_ratio",
    "debt_ratio",
    "expense_ratio",
    "balance_min",
    "balance_max",
    "balance_mean",
    "balance_monthly_trend",
    "txn_size_mean",
    "txn_size_median",
    "txn_size_variance",
    "credit_frequency",
    "debit_frequency",
    "upi_frequency",
    "atm_frequency",
    "online_spend_ratio",
    "merchant_diversity",
    "subscription_count",
    "cashflow_volatility",
    *(f"pct_{c.lower()}" for c in _CATEGORY_FEATURES),
    *(f"freq_{p.lower()}" for p in _PAYMENT_FEATURES),
)

_ONLINE_MODES = {"UPI", "NEFT", "IMPS", "RTGS"}
_OFFLINE_MODES = {"ATM", "POS"}


def build_feature_row(
    profile: FinancialProfile,
    summary: BehaviourSummary,
) -> dict[str, Any]:
    """Build a single feature row (dict) for one customer."""
    total_txns = max(summary.n_transactions, 1)
    payment_freq = summary.payment_mode_frequency
    total_payment = sum(payment_freq.values())

    credit_count = _credit_count(summary)
    debit_count = summary.n_transactions - credit_count

    online = sum(v for k, v in payment_freq.items() if k in _ONLINE_MODES)
    offline = sum(v for k, v in payment_freq.items() if k in _OFFLINE_MODES)
    online_offline_total = online + offline

    category_pct = _category_percentages(summary)
    subscription_count = int(profile.expected_cashflow.get("subscription_count", 0))

    row: dict[str, Any] = {
        "customer_id": profile.customer_id,
        "avg_income": float(profile.income) if profile.income is not None else 0.0,
        "income_consistency": profile.income_stability or 0.0,
        "avg_monthly_spend": float(profile.monthly_spend) if profile.monthly_spend else 0.0,
        "avg_monthly_saving": float(profile.monthly_saving) if profile.monthly_saving else 0.0,
        "savings_rate": profile.savings_ratio or 0.0,
        "investment_ratio": profile.investment_ratio or 0.0,
        "emi_ratio": profile.emi_ratio or 0.0,
        "debt_ratio": profile.debt_ratio or 0.0,
        "expense_ratio": summary.expense_ratio,
        "balance_min": summary.balance_min if summary.balance_min is not None else 0.0,
        "balance_max": summary.balance_max if summary.balance_max is not None else 0.0,
        "balance_mean": summary.balance_mean if summary.balance_mean is not None else 0.0,
        "balance_monthly_trend": summary.balance_monthly_trend,
        "txn_size_mean": summary.txn_size_mean,
        "txn_size_median": summary.txn_size_median,
        "txn_size_variance": summary.txn_size_variance,
        "credit_frequency": credit_count / total_txns,
        "debit_frequency": debit_count / total_txns,
        "upi_frequency": payment_freq.get("UPI", 0) / total_txns,
        "atm_frequency": payment_freq.get("ATM", 0) / total_txns,
        "online_spend_ratio": (online / online_offline_total) if online_offline_total else 0.0,
        "merchant_diversity": len(summary.merchant_frequency) / total_txns,
        "subscription_count": subscription_count,
        "cashflow_volatility": summary.cashflow_volatility,
    }

    for cat in _CATEGORY_FEATURES:
        row[f"pct_{cat.lower()}"] = category_pct.get(cat, 0.0)
    for mode in _PAYMENT_FEATURES:
        denom = total_payment if total_payment else 1
        row[f"freq_{mode.lower()}"] = payment_freq.get(mode, 0) / denom

    return {col: row[col] for col in FEATURE_COLUMNS}


def build_feature_table(
    pairs: list[tuple[FinancialProfile, BehaviourSummary]],
) -> pd.DataFrame:
    """Build the ML feature table (one row per customer) from profile/summary pairs."""
    rows = [build_feature_row(profile, summary) for profile, summary in pairs]
    if not rows:
        return pd.DataFrame(columns=list(FEATURE_COLUMNS))
    return pd.DataFrame(rows, columns=list(FEATURE_COLUMNS))


def _credit_count(summary: BehaviourSummary) -> int:
    """Approximate credit transaction count from salary + incoming signals."""
    # payment_mode_frequency does not separate direction; use category frequency
    # for salary/transfer credits as a proxy, falling back to 0.
    return int(summary.category_frequency.get("Salary", 0))


def _category_percentages(summary: BehaviourSummary) -> dict[str, float]:
    total = sum(summary.category_frequency.values())
    if total == 0:
        return {}
    return {cat: count / total for cat, count in summary.category_frequency.items()}
