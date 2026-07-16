"""Pydantic response models for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    max_upload_mb: float | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    request_id: str | None = None


class StatementUploadResponse(BaseModel):
    status: str
    customer_id: str
    filename: str
    file_type: str | None = None
    pdf_kind: str | None = None
    transactions_ingested: int = 0
    note: str | None = None


class TransactionOut(BaseModel):
    transaction_id: str
    customer_id: str
    date: datetime
    merchant: str | None = None
    description: str
    debit: float | None = None
    credit: float | None = None
    balance: float | None = None
    currency: str = "INR"
    bank: str | None = None
    payment_mode: str | None = None
    category: str | None = None
    category_confidence: float | None = None


class TransactionListResponse(BaseModel):
    customer_id: str | None = None
    count: int
    transactions: list[TransactionOut]


class ProfileResponse(BaseModel):
    customer_id: str
    income: float | None = None
    income_stability: float | None = None
    monthly_spend: float | None = None
    monthly_saving: float | None = None
    savings_ratio: float | None = None
    investment_ratio: float | None = None
    emi_ratio: float | None = None
    debt_ratio: float | None = None
    preferred_merchants: list[str] = []
    preferred_payment_modes: list[str] = []
    expected_cashflow: dict[str, Any] = {}


class FeatureResponse(BaseModel):
    customer_id: str
    features: dict[str, Any]


class SyntheticResponse(BaseModel):
    n: int
    method: str
    count: int
    metrics: dict[str, Any] = {}
    rows: list[dict[str, Any]]
