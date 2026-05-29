"""Canonical transaction contract (frozen pydantic v2 model)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CanonicalTransaction(BaseModel):
    """Single normalized bank transaction — do not mutate after creation."""

    model_config = ConfigDict(frozen=True)

    transaction_id: str
    date: datetime
    merchant: str | None = None
    description: str
    debit: Decimal | None = None
    credit: Decimal | None = None
    balance: Decimal | None = None
    currency: str = Field(default="INR")
    bank: str | None = None
    reference_number: str | None = None
    account_type: str | None = None
    payment_mode: str | None = None
    category: str | None = None
    category_confidence: float | None = None
