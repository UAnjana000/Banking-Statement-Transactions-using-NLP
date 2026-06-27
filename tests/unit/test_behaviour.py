"""Tests for behaviour summary analysis."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from tests.helpers.synthetic_txns import build_known_history

from finunderwrite.behaviour.summary import analyze_behaviour
from finunderwrite.contracts.transaction import CanonicalTransaction


def test_empty_history() -> None:
    summary = analyze_behaviour([], "cust-empty")
    assert summary.n_transactions == 0
    assert summary.monthly_spend == 0.0
    assert summary.balance_mean is None
    assert summary.salary_detected is False


def test_known_history_totals() -> None:
    txns = build_known_history(months=6)
    summary = analyze_behaviour(txns, "cust-1")

    assert summary.n_transactions == len(txns)
    assert summary.incoming_total == 360000.0  # 60000 * 6
    assert summary.outgoing_total > 0
    assert summary.salary_detected is True
    assert summary.salary_amount == 60000.0
    assert 0.0 <= summary.expense_ratio <= 1.0
    assert summary.balance_mean is not None


def test_ratios_bounded_and_consistent() -> None:
    txns = build_known_history(months=4)
    summary = analyze_behaviour(txns, "cust-2")
    # net = incoming - outgoing; savings_ratio = net/incoming
    expected_savings = round(summary.net_cashflow / summary.incoming_total, 4)
    assert summary.savings_ratio == expected_savings


def test_missing_balance_does_not_explode() -> None:
    txns = [
        CanonicalTransaction(
            transaction_id="a",
            date=datetime(2025, 1, 1),
            description="UPI-SALARY",
            credit=Decimal("50000"),
        ),
        CanonicalTransaction(
            transaction_id="b",
            date=datetime(2025, 1, 5),
            description="UPI-SWIGGY",
            debit=Decimal("500"),
        ),
    ]
    summary = analyze_behaviour(txns, "cust-3")
    assert summary.balance_min is None
    assert summary.balance_mean is None
    assert summary.balance_daily_trend == 0.0


def test_short_history_single_txn() -> None:
    txns = [
        CanonicalTransaction(
            transaction_id="only",
            date=datetime(2025, 1, 1),
            description="UPI-TEST",
            debit=Decimal("100"),
            balance=Decimal("900"),
        )
    ]
    summary = analyze_behaviour(txns, "cust-4")
    assert summary.n_transactions == 1
    assert summary.cashflow_volatility == 0.0
    assert summary.balance_daily_trend == 0.0


def test_weekend_ratio_range() -> None:
    txns = build_known_history(months=3)
    summary = analyze_behaviour(txns, "cust-5")
    assert 0.0 <= summary.weekend_spend_ratio <= 1.0
    assert 0.0 <= summary.merchant_loyalty <= 1.0
