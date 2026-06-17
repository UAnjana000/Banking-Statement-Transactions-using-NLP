"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from finunderwrite.persistence.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EnrichmentCache(Base):
    """Cached merchant enrichment results (populated by the offline batch)."""

    __tablename__ = "enrichment_cache"

    merchant: Mapped[str] = mapped_column(String(255), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(64), default="unknown")
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class EnrichmentQueue(Base):
    """Merchants awaiting offline enrichment (populated on cache miss)."""

    __tablename__ = "enrichment_queue"

    merchant: Mapped[str] = mapped_column(String(255), primary_key=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class LlmCategoryCache(Base):
    """Cached Tier 3 LLM categorization results, keyed by a stable hash."""

    __tablename__ = "llm_category_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class TransactionRecord(Base):
    """Persisted normalized transaction."""

    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    date: Mapped[datetime] = mapped_column(DateTime, index=True)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    debit: Mapped[float | None] = mapped_column(Float, nullable=True)
    credit: Mapped[float | None] = mapped_column(Float, nullable=True)
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    bank: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ProfileRecord(Base):
    """Persisted FinancialProfile payload (JSON) per customer."""

    __tablename__ = "profiles"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class FeatureRecord(Base):
    """Persisted underwriting feature row (JSON) per customer."""

    __tablename__ = "features"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class SyntheticDataset(Base):
    """Registry of pre-generated synthetic datasets served by the API."""

    __tablename__ = "synthetic_datasets"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    n: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(32))
    path: Mapped[str] = mapped_column(Text)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
