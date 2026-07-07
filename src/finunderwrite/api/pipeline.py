"""Shared request-path helpers: parse -> normalize -> enrich -> persist."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger

from finunderwrite.contracts.transaction import CanonicalTransaction
from finunderwrite.inventory.profiler import FileProfile
from finunderwrite.normalize.normalizer import normalize_dataframe
from finunderwrite.parser import get_parser
from finunderwrite.schema_detection.mapper import detect_schema


def parse_and_normalize(
    path: Path,
    profile: FileProfile,
) -> list[CanonicalTransaction]:
    """Parse a (non-scanned) file into normalized CanonicalTransactions."""
    parser = get_parser(profile)
    if parser is None:
        msg = f"No parser available for {profile.file_type}"
        raise ValueError(msg)
    result = parser.parse(path, profile)
    df = result.df()
    mapping = detect_schema(df)
    return normalize_dataframe(df, mapping, bank=profile.detected_bank)


def enrich_transactions(
    transactions: list[CanonicalTransaction],
) -> list[CanonicalTransaction]:
    """Fill merchant/payment_mode and category/confidence. Never raises per-row."""
    from finunderwrite.merchant.categorize import Categorizer
    from finunderwrite.merchant.extract import MerchantExtractor

    extractor = MerchantExtractor()
    categorizer = Categorizer()
    enriched: list[CanonicalTransaction] = []
    for txn in transactions:
        try:
            txn = extractor.apply_to_transaction(txn)
            category, confidence = categorizer.categorize(txn.merchant, txn.description)
            txn = txn.model_copy(update={"category": category, "category_confidence": confidence})
        except Exception as exc:  # enrichment must never break ingestion
            logger.warning("Enrichment failed for {}: {}", txn.transaction_id, exc)
        enriched.append(txn)
    return enriched


def transaction_to_record(txn: CanonicalTransaction) -> dict[str, Any]:
    """Convert a CanonicalTransaction to a persistence-ready dict."""

    def _f(value: Decimal | None) -> float | None:
        return float(value) if value is not None else None

    return {
        "transaction_id": txn.transaction_id,
        "date": txn.date,
        "merchant": txn.merchant,
        "description": txn.description,
        "debit": _f(txn.debit),
        "credit": _f(txn.credit),
        "balance": _f(txn.balance),
        "currency": txn.currency,
        "bank": txn.bank,
        "payment_mode": txn.payment_mode,
        "category": txn.category,
        "category_confidence": txn.category_confidence,
    }


def record_to_transaction(record: dict[str, Any]) -> CanonicalTransaction:
    """Convert a persisted transaction dict back to a CanonicalTransaction."""

    def _d(value: float | None) -> Decimal | None:
        return Decimal(str(value)) if value is not None else None

    return CanonicalTransaction(
        transaction_id=record["transaction_id"],
        date=record["date"],
        merchant=record.get("merchant"),
        description=record.get("description", ""),
        debit=_d(record.get("debit")),
        credit=_d(record.get("credit")),
        balance=_d(record.get("balance")),
        currency=record.get("currency", "INR"),
        bank=record.get("bank"),
        payment_mode=record.get("payment_mode"),
        category=record.get("category"),
        category_confidence=record.get("category_confidence"),
    )
