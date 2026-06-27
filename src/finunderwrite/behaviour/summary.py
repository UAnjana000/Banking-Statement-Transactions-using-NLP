"""Deterministic behaviour learning over a single customer's transactions.

Pure pandas/numpy. No torch, no network. Designed to degrade gracefully on
short histories and missing balances rather than raising.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from finunderwrite.contracts.transaction import CanonicalTransaction

_INVESTMENT_CATEGORIES = {"Investments"}
_EMI_CATEGORIES = {"EMI"}
_DEBT_CATEGORIES = {"Loan", "EMI"}
_SALARY_MIN_OCCURRENCES = 2


class BehaviourSummary(BaseModel):
    """Aggregated behavioural metrics for one customer."""

    customer_id: str
    n_transactions: int
    first_date: datetime | None = None
    last_date: datetime | None = None
    months_covered: float = 0.0

    monthly_spend: float = 0.0
    weekly_spend: float = 0.0
    weekend_spend_ratio: float = 0.0

    incoming_total: float = 0.0
    outgoing_total: float = 0.0
    net_cashflow: float = 0.0
    monthly_saving: float = 0.0

    savings_ratio: float = 0.0
    investment_ratio: float = 0.0
    emi_ratio: float = 0.0
    debt_ratio: float = 0.0
    expense_ratio: float = 0.0

    balance_min: float | None = None
    balance_max: float | None = None
    balance_mean: float | None = None
    balance_daily_trend: float = 0.0
    balance_monthly_trend: float = 0.0
    balance_quarterly_trend: float = 0.0

    txn_size_mean: float = 0.0
    txn_size_median: float = 0.0
    txn_size_variance: float = 0.0

    merchant_frequency: dict[str, int] = Field(default_factory=dict)
    category_frequency: dict[str, int] = Field(default_factory=dict)
    payment_mode_frequency: dict[str, int] = Field(default_factory=dict)
    merchant_loyalty: float = 0.0

    cashflow_volatility: float = 0.0

    salary_detected: bool = False
    salary_amount: float | None = None


def _to_float(value: Decimal | float | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _transactions_to_frame(transactions: list[CanonicalTransaction]) -> pd.DataFrame:
    rows = []
    for txn in transactions:
        debit = _to_float(txn.debit)
        credit = _to_float(txn.credit)
        rows.append(
            {
                "date": pd.Timestamp(txn.date),
                "debit": debit,
                "credit": credit,
                "amount": credit - debit,
                "balance": float(txn.balance) if txn.balance is not None else np.nan,
                "merchant": txn.merchant or "",
                "category": txn.category or "",
                "payment_mode": txn.payment_mode or "",
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date").reset_index(drop=True)
    return df


def _slope(x: np.ndarray, y: np.ndarray) -> float:
    """Least-squares slope; 0.0 when insufficient/degenerate data."""
    if len(x) < 2 or np.all(x == x[0]):
        return 0.0
    try:
        slope = np.polyfit(x, y, 1)[0]
    except (np.linalg.LinAlgError, ValueError):
        return 0.0
    return float(slope) if np.isfinite(slope) else 0.0


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator / denominator)


def analyze_behaviour(
    transactions: list[CanonicalTransaction],
    customer_id: str,
) -> BehaviourSummary:
    """Compute a BehaviourSummary for one customer. Never raises on empty/short input."""
    df = _transactions_to_frame(transactions)
    if df.empty:
        return BehaviourSummary(customer_id=customer_id, n_transactions=0)

    first_date = df["date"].iloc[0].to_pydatetime()
    last_date = df["date"].iloc[-1].to_pydatetime()
    days_covered = max((last_date - first_date).days, 0)
    months_covered = max(days_covered / 30.0, 1.0 / 30.0)
    weeks_covered = max(days_covered / 7.0, 1.0 / 7.0)

    incoming_total = float(df["credit"].sum())
    outgoing_total = float(df["debit"].sum())
    net_cashflow = incoming_total - outgoing_total

    monthly_spend = outgoing_total / months_covered
    weekly_spend = outgoing_total / weeks_covered
    monthly_saving = net_cashflow / months_covered

    weekend_mask = df["date"].dt.dayofweek >= 5
    weekend_spend = float(df.loc[weekend_mask, "debit"].sum())
    weekend_spend_ratio = _safe_ratio(weekend_spend, outgoing_total)

    investment_spend = float(df.loc[df["category"].isin(_INVESTMENT_CATEGORIES), "debit"].sum())
    emi_spend = float(df.loc[df["category"].isin(_EMI_CATEGORIES), "debit"].sum())
    debt_spend = float(df.loc[df["category"].isin(_DEBT_CATEGORIES), "debit"].sum())

    savings_ratio = _safe_ratio(net_cashflow, incoming_total)
    investment_ratio = _safe_ratio(investment_spend, incoming_total)
    emi_ratio = _safe_ratio(emi_spend, incoming_total)
    debt_ratio = _safe_ratio(debt_spend, incoming_total)
    expense_ratio = _safe_ratio(outgoing_total, incoming_total)

    balances = df["balance"].dropna()
    balance_min = float(balances.min()) if not balances.empty else None
    balance_max = float(balances.max()) if not balances.empty else None
    balance_mean = float(balances.mean()) if not balances.empty else None

    balance_daily_trend, balance_monthly_trend, balance_quarterly_trend = _balance_trends(df)

    debits = df.loc[df["debit"] > 0, "debit"]
    txn_size_mean = float(debits.mean()) if not debits.empty else 0.0
    txn_size_median = float(debits.median()) if not debits.empty else 0.0
    txn_size_variance = float(debits.var(ddof=0)) if len(debits) > 1 else 0.0

    merchant_frequency = _frequency(df, "merchant")
    category_frequency = _frequency(df, "category")
    payment_mode_frequency = _frequency(df, "payment_mode")
    merchant_loyalty = _merchant_loyalty(merchant_frequency)

    cashflow_volatility = _cashflow_volatility(df)

    salary_detected, salary_amount = _detect_salary(df)

    return BehaviourSummary(
        customer_id=customer_id,
        n_transactions=len(df),
        first_date=first_date,
        last_date=last_date,
        months_covered=round(months_covered, 4),
        monthly_spend=round(monthly_spend, 2),
        weekly_spend=round(weekly_spend, 2),
        weekend_spend_ratio=round(weekend_spend_ratio, 4),
        incoming_total=round(incoming_total, 2),
        outgoing_total=round(outgoing_total, 2),
        net_cashflow=round(net_cashflow, 2),
        monthly_saving=round(monthly_saving, 2),
        savings_ratio=round(savings_ratio, 4),
        investment_ratio=round(investment_ratio, 4),
        emi_ratio=round(emi_ratio, 4),
        debt_ratio=round(debt_ratio, 4),
        expense_ratio=round(expense_ratio, 4),
        balance_min=balance_min,
        balance_max=balance_max,
        balance_mean=round(balance_mean, 2) if balance_mean is not None else None,
        balance_daily_trend=round(balance_daily_trend, 4),
        balance_monthly_trend=round(balance_monthly_trend, 4),
        balance_quarterly_trend=round(balance_quarterly_trend, 4),
        txn_size_mean=round(txn_size_mean, 2),
        txn_size_median=round(txn_size_median, 2),
        txn_size_variance=round(txn_size_variance, 2),
        merchant_frequency=merchant_frequency,
        category_frequency=category_frequency,
        payment_mode_frequency=payment_mode_frequency,
        merchant_loyalty=round(merchant_loyalty, 4),
        cashflow_volatility=round(cashflow_volatility, 4),
        salary_detected=salary_detected,
        salary_amount=round(salary_amount, 2) if salary_amount is not None else None,
    )


def _balance_trends(df: pd.DataFrame) -> tuple[float, float, float]:
    balances = df.dropna(subset=["balance"])
    if len(balances) < 2:
        return 0.0, 0.0, 0.0

    indexed = balances.set_index("date")["balance"]
    origin = indexed.index[0]
    days = (indexed.index - origin).days.to_numpy(dtype=float)
    daily = _slope(days, indexed.to_numpy(dtype=float))

    monthly_series = indexed.resample("ME").last().dropna()
    if len(monthly_series) >= 2:
        m_x = np.arange(len(monthly_series), dtype=float)
        monthly = _slope(m_x, monthly_series.to_numpy(dtype=float))
    else:
        monthly = 0.0

    quarterly_series = indexed.resample("QE").last().dropna()
    if len(quarterly_series) >= 2:
        q_x = np.arange(len(quarterly_series), dtype=float)
        quarterly = _slope(q_x, quarterly_series.to_numpy(dtype=float))
    else:
        quarterly = 0.0

    return daily, monthly, quarterly


def _frequency(df: pd.DataFrame, column: str) -> dict[str, int]:
    counts = df.loc[df[column] != "", column].value_counts()
    return {str(k): int(v) for k, v in counts.items()}


def _merchant_loyalty(merchant_frequency: dict[str, int]) -> float:
    """Share of merchant-tagged transactions going to the single top merchant."""
    if not merchant_frequency:
        return 0.0
    total = sum(merchant_frequency.values())
    if total == 0:
        return 0.0
    return max(merchant_frequency.values()) / total


def _cashflow_volatility(df: pd.DataFrame) -> float:
    """Coefficient of variation of monthly net cashflow."""
    monthly = df.set_index("date")["amount"].resample("ME").sum()
    if len(monthly) < 2:
        return 0.0
    mean = float(monthly.mean())
    std = float(monthly.std(ddof=0))
    if mean == 0:
        return 0.0
    return abs(std / mean)


def _detect_salary(df: pd.DataFrame) -> tuple[bool, float | None]:
    """Salary = large, roughly-monthly recurring credits."""
    credits = df.loc[df["credit"] > 0].copy()
    if len(credits) < _SALARY_MIN_OCCURRENCES:
        return False, None

    threshold = credits["credit"].quantile(0.75)
    large = credits.loc[credits["credit"] >= threshold]
    if len(large) < _SALARY_MIN_OCCURRENCES:
        return False, None

    # Cluster the largest recurring credit by rounded amount.
    large = large.assign(bucket=(large["credit"] / 1000).round())
    top_bucket = large.groupby("bucket").size().idxmax()
    salary_rows = large.loc[large["bucket"] == top_bucket]
    if len(salary_rows) < _SALARY_MIN_OCCURRENCES:
        return False, None

    return True, float(salary_rows["credit"].median())
