"""Tests for the profile builder."""

from __future__ import annotations

from decimal import Decimal

from tests.helpers.synthetic_txns import build_known_history

from finunderwrite.contracts.profile import FinancialProfile
from finunderwrite.profile.builder import build_profile


def test_build_profile_known_history() -> None:
    txns = build_known_history(months=6, salary=Decimal("60000"))
    profile = build_profile("cust-1", txns)

    assert isinstance(profile, FinancialProfile)
    assert profile.customer_id == "cust-1"
    assert profile.income is not None
    assert abs(float(profile.income) - 60000) < 1
    assert profile.income_stability is not None
    assert 0.0 <= profile.income_stability <= 1.0

    assert "Netflix" in profile.preferred_merchants or "Spotify" in profile.preferred_merchants
    assert "UPI" in profile.preferred_payment_modes

    ec = profile.expected_cashflow
    assert ec["subscription_count"] >= 2
    assert "spend_by_category" in ec
    assert ec["expected_monthly_income"] > 0


def test_build_profile_empty_history() -> None:
    profile = build_profile("cust-empty", [])
    assert profile.customer_id == "cust-empty"
    assert profile.income is None
    assert profile.income_stability is None
    assert profile.preferred_merchants == []
    assert profile.expected_cashflow["subscription_count"] == 0


def test_profile_is_frozen() -> None:
    profile = build_profile("cust-2", build_known_history(months=3))
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        profile.customer_id = "changed"  # type: ignore[misc]
