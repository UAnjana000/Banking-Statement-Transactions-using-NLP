"""Normalize raw tables into CanonicalTransaction records."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
from dateutil import parser as date_parser
from loguru import logger

from finunderwrite.contracts.transaction import CanonicalTransaction
from finunderwrite.schema_detection.mapper import ColumnMapping

_PAYMENT_MODE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)^UPI[-/]"), "UPI"),
    (re.compile(r"(?i)^NEFT"), "NEFT"),
    (re.compile(r"(?i)^IMPS"), "IMPS"),
    (re.compile(r"(?i)^ATM"), "ATM"),
    (re.compile(r"(?i)^POS"), "POS"),
    (re.compile(r"(?i)^RTGS"), "RTGS"),
]


def normalize_dataframe(
    df: pd.DataFrame,
    mapping: ColumnMapping,
    *,
    bank: str | None = None,
    currency: str = "INR",
    signed_amount_column: str | None = None,
) -> list[CanonicalTransaction]:
    """Apply *mapping* and return validated canonical transactions."""
    if df.empty:
        msg = "Cannot normalize empty DataFrame"
        raise ValueError(msg)

    signed_col = signed_amount_column or df.attrs.get("signed_amount_column")
    transactions: list[CanonicalTransaction] = []

    for idx, row in df.iterrows():
        try:
            txn = _row_to_transaction(
                row,
                mapping,
                bank=bank,
                currency=currency,
                signed_amount_column=str(signed_col) if signed_col else None,
                row_index=int(idx) if isinstance(idx, int) else len(transactions),
            )
            transactions.append(txn)
        except Exception as exc:
            logger.warning("Skipping row {}: {}", idx, exc)

    if not transactions:
        msg = "No valid transactions after normalization"
        raise ValueError(msg)

    return transactions


def _row_to_transaction(
    row: pd.Series,
    mapping: ColumnMapping,
    *,
    bank: str | None,
    currency: str,
    signed_amount_column: str | None,
    row_index: int,
) -> CanonicalTransaction:
    date_col = mapping.get_column("date")
    desc_col = mapping.get_column("description")
    debit_col = mapping.get_column("debit")
    credit_col = mapping.get_column("credit")
    balance_col = mapping.get_column("balance")
    ref_col = mapping.get_column("reference_number")
    amount_col = mapping.get_column("amount") or signed_amount_column

    if date_col is None:
        msg = f"Row {row_index}: missing date column mapping"
        raise ValueError(msg)

    txn_date = _parse_date(_cell(row, date_col))
    description = _cell(row, desc_col) if desc_col else ""
    if not description:
        mapped_cols = {m.source_column for m in mapping.mappings}
        description = " ".join(
            str(v) for k, v in row.items() if k not in mapped_cols and str(v).strip()
        )[:200]

    debit: Decimal | None = None
    credit: Decimal | None = None

    if debit_col or credit_col:
        debit = _parse_amount(_cell(row, debit_col)) if debit_col else None
        credit = _parse_amount(_cell(row, credit_col)) if credit_col else None
    elif amount_col:
        debit, credit = _split_signed_amount(_cell(row, amount_col))

    balance = _parse_amount(_cell(row, balance_col)) if balance_col else None
    reference = _cell(row, ref_col) if ref_col else None
    payment_mode = infer_payment_mode(description)

    return CanonicalTransaction(
        transaction_id=str(uuid.uuid4()),
        date=txn_date,
        merchant=None,
        description=description,
        debit=debit,
        credit=credit,
        balance=balance,
        currency=currency,
        bank=bank,
        reference_number=reference or None,
        account_type=None,
        payment_mode=payment_mode,
        category=None,
        category_confidence=None,
    )


def _cell(row: pd.Series, col: str | None) -> str:
    if col is None:
        return ""
    val = row.get(col, "")
    if pd.isna(val):
        return ""
    return str(val).strip()


def _parse_date(value: str) -> datetime:
    if not value:
        msg = "Empty date value"
        raise ValueError(msg)
    value = value.strip()
    try:
        # dayfirst=True for Indian DD/MM/YYYY formats
        return date_parser.parse(value, dayfirst=True)
    except (ValueError, OverflowError) as exc:
        msg = f"Unparseable date: {value}"
        raise ValueError(msg) from exc


def _parse_amount(value: str) -> Decimal | None:
    if not value or value.lower() in {"nan", "none", "-", ""}:
        return None
    cleaned = value.replace(",", "").replace("₹", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        msg = f"Invalid amount: {value}"
        raise ValueError(msg) from exc


def _split_signed_amount(value: str) -> tuple[Decimal | None, Decimal | None]:
    amount = _parse_amount(value)
    if amount is None:
        return None, None
    if amount < 0:
        return abs(amount), None
    if amount > 0:
        return None, amount
    return None, None


def infer_payment_mode(description: str) -> str | None:
    for pattern, mode in _PAYMENT_MODE_RULES:
        if pattern.search(description):
            return mode
    return None
