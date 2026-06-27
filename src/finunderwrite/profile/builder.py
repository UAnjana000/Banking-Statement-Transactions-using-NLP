"""Build a FinancialProfile from behaviour + recurring analysis.

Deterministic. Maps into the frozen FinancialProfile contract; richer detail
(spend-by-category, recurring items, expected monthly cashflow) is carried in
the ``expected_cashflow`` free-form dict so the contract need not change.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from finunderwrite.behaviour.recurring import RecurringItem, detect_recurring
from finunderwrite.behaviour.summary import BehaviourSummary, analyze_behaviour
from finunderwrite.contracts.profile import FinancialProfile
from finunderwrite.contracts.transaction import CanonicalTransaction

_TOP_N = 5


def build_profile(
    customer_id: str,
    transactions: list[CanonicalTransaction],
) -> FinancialProfile:
    """Assemble a validated FinancialProfile for one customer."""
    summary = analyze_behaviour(transactions, customer_id)
    recurring = detect_recurring(transactions)
    return build_profile_from(customer_id, summary, recurring)


def build_profile_from(
    customer_id: str,
    summary: BehaviourSummary,
    recurring: list[RecurringItem],
) -> FinancialProfile:
    """Assemble a FinancialProfile from precomputed behaviour + recurring items."""
    income = _income(summary, recurring)
    income_stability = _income_stability(summary, recurring)

    preferred_merchants = _top_keys(summary.merchant_frequency, _TOP_N)
    preferred_payment_modes = _top_keys(summary.payment_mode_frequency, _TOP_N)

    expected_cashflow: dict[str, Any] = {
        "expected_monthly_income": round(float(income), 2) if income is not None else 0.0,
        "expected_monthly_spend": summary.monthly_spend,
        "expected_monthly_saving": summary.monthly_saving,
        "net_monthly_cashflow": round(summary.monthly_saving, 2),
        "spend_by_category": _spend_by_category(summary),
        "cashflow_volatility": summary.cashflow_volatility,
        "recurring": [item.model_dump() for item in recurring],
        "subscription_count": sum(1 for it in recurring if it.category == "Subscription"),
        "balance_mean": summary.balance_mean,
        "months_covered": summary.months_covered,
    }

    return FinancialProfile(
        customer_id=customer_id,
        income=income,
        income_stability=income_stability,
        monthly_spend=Decimal(str(summary.monthly_spend)),
        monthly_saving=Decimal(str(summary.monthly_saving)),
        savings_ratio=summary.savings_ratio,
        investment_ratio=summary.investment_ratio,
        emi_ratio=summary.emi_ratio,
        debt_ratio=summary.debt_ratio,
        preferred_merchants=preferred_merchants,
        preferred_payment_modes=preferred_payment_modes,
        expected_cashflow=expected_cashflow,
    )


def _income(summary: BehaviourSummary, recurring: list[RecurringItem]) -> Decimal | None:
    salary_items = [it for it in recurring if it.category == "Salary"]
    if salary_items:
        best = max(salary_items, key=lambda it: it.confidence)
        return Decimal(str(round(best.median_amount, 2)))
    if summary.salary_detected and summary.salary_amount is not None:
        return Decimal(str(round(summary.salary_amount, 2)))
    return None


def _income_stability(summary: BehaviourSummary, recurring: list[RecurringItem]) -> float | None:
    """Confidence of the detected salary stream (0..1); None if no income signal."""
    salary_items = [it for it in recurring if it.category == "Salary"]
    if salary_items:
        return round(max(it.confidence for it in salary_items), 4)
    if summary.salary_detected:
        return 0.5
    return None


def _spend_by_category(summary: BehaviourSummary) -> dict[str, float]:
    total = sum(summary.category_frequency.values())
    if total == 0:
        return {}
    return {cat: round(count / total, 4) for cat, count in summary.category_frequency.items()}


def _top_keys(frequency: dict[str, int], n: int) -> list[str]:
    return [k for k, _ in sorted(frequency.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]
