"""Data-access helpers for enrichment cache/queue and LLM cache."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from finunderwrite.persistence.database import get_session
from finunderwrite.persistence.models import (
    EnrichmentCache,
    EnrichmentQueue,
    FeatureRecord,
    LlmCategoryCache,
    ProfileRecord,
    SyntheticDataset,
    TransactionRecord,
)


def get_cached(merchant: str) -> dict[str, Any] | None:
    """Return the cached enrichment payload for *merchant*, or None."""
    with get_session() as session:
        row = session.get(EnrichmentCache, merchant)
        if row is None:
            return None
        return {
            "merchant": row.merchant,
            "payload": dict(row.payload or {}),
            "source": row.source,
            "success": row.success,
            "fetched_at": row.fetched_at,
        }


def upsert_cache(
    merchant: str,
    payload: dict[str, Any],
    *,
    source: str,
    success: bool,
) -> None:
    """Insert or update a cache entry for *merchant*."""
    with get_session() as session:
        row = session.get(EnrichmentCache, merchant)
        if row is None:
            row = EnrichmentCache(merchant=merchant)
            session.add(row)
        row.payload = payload
        row.source = source
        row.success = success
        row.fetched_at = datetime.now(UTC)


def enqueue(merchant: str) -> None:
    """Add *merchant* to the offline enrichment queue if not already present."""
    with get_session() as session:
        existing = session.get(EnrichmentQueue, merchant)
        if existing is None:
            session.add(EnrichmentQueue(merchant=merchant))


def list_queue() -> list[str]:
    """Return all queued merchant names."""
    with get_session() as session:
        rows = session.execute(select(EnrichmentQueue.merchant)).scalars().all()
        return list(rows)


def record_queue_error(merchant: str, error: str) -> None:
    """Increment attempts and store the last error for a queued merchant."""
    with get_session() as session:
        row = session.get(EnrichmentQueue, merchant)
        if row is not None:
            row.attempts += 1
            row.last_error = error


def resolve_queue(merchant: str) -> None:
    """Remove *merchant* from the queue after successful enrichment."""
    with get_session() as session:
        row = session.get(EnrichmentQueue, merchant)
        if row is not None:
            session.delete(row)


def get_llm_category(key: str) -> tuple[str, float] | None:
    """Return a cached Tier 3 category result for *key*, or None."""
    with get_session() as session:
        row = session.get(LlmCategoryCache, key)
        if row is None:
            return None
        return row.category, row.confidence


def put_llm_category(
    key: str,
    category: str,
    confidence: float,
    *,
    merchant: str | None = None,
) -> None:
    """Cache a Tier 3 category result under *key*."""
    with get_session() as session:
        row = session.get(LlmCategoryCache, key)
        if row is None:
            row = LlmCategoryCache(key=key)
            session.add(row)
        row.merchant = merchant
        row.category = category
        row.confidence = confidence
        row.created_at = datetime.now(UTC)


# --- transactions -----------------------------------------------------------


def save_transactions(customer_id: str, transactions: list[dict[str, Any]]) -> int:
    """Upsert normalized transaction dicts for a customer. Returns count."""
    saved = 0
    with get_session() as session:
        for txn in transactions:
            row = session.get(TransactionRecord, txn["transaction_id"])
            if row is None:
                row = TransactionRecord(transaction_id=txn["transaction_id"])
                session.add(row)
            row.customer_id = customer_id
            row.date = txn["date"]
            row.merchant = txn.get("merchant")
            row.description = txn.get("description", "")
            row.debit = txn.get("debit")
            row.credit = txn.get("credit")
            row.balance = txn.get("balance")
            row.currency = txn.get("currency", "INR")
            row.bank = txn.get("bank")
            row.payment_mode = txn.get("payment_mode")
            row.category = txn.get("category")
            row.category_confidence = txn.get("category_confidence")
            saved += 1
    return saved


def list_transactions(
    customer_id: str | None = None,
    *,
    category: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return filterable normalized transactions as plain dicts."""
    with get_session() as session:
        stmt = select(TransactionRecord)
        if customer_id:
            stmt = stmt.where(TransactionRecord.customer_id == customer_id)
        if category:
            stmt = stmt.where(TransactionRecord.category == category)
        stmt = stmt.order_by(TransactionRecord.date.desc()).limit(limit).offset(offset)
        rows = session.execute(stmt).scalars().all()
        return [_transaction_to_dict(r) for r in rows]


def _transaction_to_dict(row: TransactionRecord) -> dict[str, Any]:
    return {
        "transaction_id": row.transaction_id,
        "customer_id": row.customer_id,
        "date": row.date,
        "merchant": row.merchant,
        "description": row.description,
        "debit": row.debit,
        "credit": row.credit,
        "balance": row.balance,
        "currency": row.currency,
        "bank": row.bank,
        "payment_mode": row.payment_mode,
        "category": row.category,
        "category_confidence": row.category_confidence,
    }


# --- profiles & features ----------------------------------------------------


def save_profile(customer_id: str, payload: dict[str, Any]) -> None:
    with get_session() as session:
        row = session.get(ProfileRecord, customer_id)
        if row is None:
            row = ProfileRecord(customer_id=customer_id)
            session.add(row)
        row.payload = payload
        row.updated_at = datetime.now(UTC)


def get_profile(customer_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.get(ProfileRecord, customer_id)
        return dict(row.payload) if row is not None else None


def save_feature(customer_id: str, payload: dict[str, Any]) -> None:
    with get_session() as session:
        row = session.get(FeatureRecord, customer_id)
        if row is None:
            row = FeatureRecord(customer_id=customer_id)
            session.add(row)
        row.payload = payload
        row.updated_at = datetime.now(UTC)


def get_feature(customer_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.get(FeatureRecord, customer_id)
        return dict(row.payload) if row is not None else None


# --- synthetic dataset registry ---------------------------------------------


def register_synthetic_dataset(
    name: str,
    n: int,
    method: str,
    path: str,
    metrics: dict[str, Any],
) -> None:
    with get_session() as session:
        row = session.get(SyntheticDataset, name)
        if row is None:
            row = SyntheticDataset(name=name)
            session.add(row)
        row.n = n
        row.method = method
        row.path = path
        row.metrics = metrics
        row.created_at = datetime.now(UTC)


def get_synthetic_dataset(n: int, method: str | None = None) -> dict[str, Any] | None:
    """Return a registered synthetic dataset by N (and optional method)."""
    with get_session() as session:
        stmt = select(SyntheticDataset).where(SyntheticDataset.n == n)
        if method:
            stmt = stmt.where(SyntheticDataset.method == method)
        row = session.execute(stmt).scalars().first()
        if row is None:
            return None
        return {
            "name": row.name,
            "n": row.n,
            "method": row.method,
            "path": row.path,
            "metrics": dict(row.metrics or {}),
        }


def list_synthetic_datasets() -> list[dict[str, Any]]:
    with get_session() as session:
        rows = session.execute(select(SyntheticDataset)).scalars().all()
        return [{"name": r.name, "n": r.n, "method": r.method, "path": r.path} for r in rows]
