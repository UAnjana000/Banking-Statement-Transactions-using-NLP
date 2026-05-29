"""Tests for normalizer."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pandas as pd

from finunderwrite.normalize.normalizer import infer_payment_mode, normalize_dataframe
from finunderwrite.schema_detection.mapper import detect_schema


def test_normalize_sbi_csv(fixtures_dir: Path) -> None:
    df = pd.read_csv(fixtures_dir / "sbi_style.csv", dtype=str)
    mapping = detect_schema(df)
    txns = normalize_dataframe(df, mapping, bank="SBI")

    assert len(txns) == 3
    assert txns[0].debit == Decimal("250.00")
    assert txns[0].credit is None
    assert txns[0].payment_mode == "UPI"
    assert txns[1].credit == Decimal("50000.00")
    assert txns[1].payment_mode == "NEFT"
    assert txns[2].payment_mode == "ATM"


def test_normalize_canara_csv(fixtures_dir: Path) -> None:
    df = pd.read_csv(fixtures_dir / "canara_style.csv", dtype=str)
    mapping = detect_schema(df)
    txns = normalize_dataframe(df, mapping, bank="Canara Bank")

    assert len(txns) == 3
    assert txns[0].debit == Decimal("1200.50")
    assert txns[2].credit == Decimal("45000.00")


def test_signed_amount_split(fixtures_dir: Path) -> None:
    df = pd.read_csv(fixtures_dir / "signed_amount.csv", dtype=str)
    mapping = detect_schema(df)
    txns = normalize_dataframe(df, mapping, signed_amount_column="Amount")

    assert txns[0].debit == Decimal("45.00")
    assert txns[0].credit is None
    assert txns[1].debit is None
    assert txns[1].credit == Decimal("1200.00")


def test_infer_payment_mode() -> None:
    assert infer_payment_mode("UPI-SWIGGY/123") == "UPI"
    assert infer_payment_mode("NEFT-CREDIT") == "NEFT"
    assert infer_payment_mode("Random purchase") is None


def test_all_transactions_validate_through_pydantic(fixtures_dir: Path) -> None:
    df = pd.read_csv(fixtures_dir / "sbi_style.csv", dtype=str)
    mapping = detect_schema(df)
    txns = normalize_dataframe(df, mapping)
    for txn in txns:
        assert txn.description
        assert txn.date.year == 2025
