"""Tests for frozen contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from finunderwrite.contracts.profile import FinancialProfile
from finunderwrite.contracts.transaction import CanonicalTransaction


def test_canonical_transaction_frozen() -> None:
    txn = CanonicalTransaction(
        transaction_id="abc",
        date=datetime(2025, 1, 15),
        description="UPI-TEST",
        debit=Decimal("10.00"),
    )
    with pytest.raises(ValidationError):
        txn.description = "changed"  # type: ignore[misc]


def test_financial_profile_stub() -> None:
    profile = FinancialProfile(customer_id="cust-1")
    assert profile.customer_id == "cust-1"
    assert profile.preferred_merchants == []
