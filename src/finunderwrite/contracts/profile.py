"""Financial profile contract (stub — builder comes in a later prompt)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FinancialProfile(BaseModel):
    """Aggregated customer financial profile — fields frozen; builder deferred."""

    model_config = ConfigDict(frozen=True)

    customer_id: str
    income: Decimal | None = None
    income_stability: float | None = None
    monthly_spend: Decimal | None = None
    monthly_saving: Decimal | None = None
    savings_ratio: float | None = None
    investment_ratio: float | None = None
    emi_ratio: float | None = None
    debt_ratio: float | None = None
    preferred_merchants: list[str] = Field(default_factory=list)
    preferred_payment_modes: list[str] = Field(default_factory=list)
    expected_cashflow: dict[str, Any] = Field(default_factory=dict)
