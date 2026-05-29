"""Tests for schema detection."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from finunderwrite.schema_detection.mapper import detect_schema, load_synonyms


def test_schema_mapping_sbi_vocabulary(fixtures_dir: Path) -> None:
    df = pd.read_csv(fixtures_dir / "sbi_style.csv", dtype=str)
    mapping = detect_schema(df)

    assert mapping.get_column("date") == "Txn Date"
    assert mapping.get_column("description") == "Description"
    assert mapping.get_column("debit") == "Debit"
    assert mapping.get_column("credit") == "Credit"
    assert mapping.get_column("balance") == "Balance"
    assert mapping.confidence_for("date") == 1.0


def test_schema_mapping_canara_vocabulary(fixtures_dir: Path) -> None:
    df = pd.read_csv(fixtures_dir / "canara_style.csv", dtype=str)
    mapping = detect_schema(df)

    assert mapping.get_column("date") == "Value Date"
    assert mapping.get_column("description") == "Particulars"
    assert mapping.get_column("debit") == "Withdrawal"
    assert mapping.get_column("credit") == "Deposit"
    assert mapping.get_column("balance") == "Closing Balance"


def test_schema_mapping_signed_amount_column(fixtures_dir: Path) -> None:
    df = pd.read_csv(fixtures_dir / "signed_amount.csv", dtype=str)
    mapping = detect_schema(df)

    assert mapping.get_column("date") == "Transaction Date"
    assert mapping.get_column("description") == "Narration"
    assert mapping.get_column("amount") == "Amount"
    assert mapping.get_column("balance") == "Balance"


def test_unmapped_columns_logged(fixtures_dir: Path) -> None:
    df = pd.read_csv(fixtures_dir / "sbi_style.csv", dtype=str)
    df["Extra Notes"] = "note"
    mapping = detect_schema(df)
    assert "Extra Notes" in mapping.unmapped_columns


def test_load_synonyms() -> None:
    synonyms = load_synonyms()
    assert "debit" in synonyms
    assert "withdrawal" in synonyms["debit"]
