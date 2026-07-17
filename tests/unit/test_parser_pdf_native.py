"""Tests for native PDF table coalescing helpers and text fallback."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from finunderwrite.inventory.profiler import profile_file
from finunderwrite.parser.pdf_native import (
    NativePdfParser,
    _coalesce_compatible_frames,
    _ensure_unique_columns,
    _unique_column_names,
    camelot_fallback_enabled,
    max_sync_pdf_pages,
    parse_statement_text,
)


def test_unique_column_names_dedupes_blanks() -> None:
    names = _unique_column_names(["Date", "", "", "Balance"])
    assert names == ["Date", "col", "col_1", "Balance"]


def test_ensure_unique_columns_allows_concat() -> None:
    a = _ensure_unique_columns(pd.DataFrame([[1, 2]], columns=["", ""]))
    b = _ensure_unique_columns(pd.DataFrame([[3, 4]], columns=["", ""]))
    combined = pd.concat([a, b], ignore_index=True)
    assert list(combined.columns) == ["col", "col_1"]
    assert len(combined) == 2


def test_coalesce_prefers_transaction_like_width() -> None:
    summary = pd.DataFrame(
        [["x", "y"]],
        columns=["Account Summary", "Available Balance"],
    )
    txns = pd.DataFrame(
        [["01/01/2025", "UPI", "10", "100"]],
        columns=["Date", "Description", "Debit", "Balance"],
    )
    junk = pd.DataFrame([[1, 2, 3]], columns=["a", "b", "c"])
    selected = _coalesce_compatible_frames([summary, txns, junk])
    assert len(selected) == 1
    assert list(selected[0].columns) == ["Date", "Description", "Debit", "Balance"]


def test_camelot_fallback_enabled_by_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("FINUNDERWRITE_ENABLE_CAMELOT_FALLBACK", raising=False)
    monkeypatch.setenv("RENDER", "true")
    assert camelot_fallback_enabled() is True


def test_camelot_fallback_can_be_disabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("FINUNDERWRITE_ENABLE_CAMELOT_FALLBACK", "false")
    assert camelot_fallback_enabled() is False


def test_max_sync_pdf_pages_defaults_low_on_render(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("FINUNDERWRITE_MAX_SYNC_PDF_PAGES", raising=False)
    monkeypatch.setenv("RENDER", "true")
    assert max_sync_pdf_pages() == 8


def test_parse_statement_text_sbi_style() -> None:
    text = (
        "State Bank of India - Synthetic Statement\n"
        "Txn Date Description Debit Credit Balance\n"
        "15/01/2025 UPI-SWIGGY 250.00 4750.00\n"
        "16/01/2025 NEFT-SALARY 50000.00 54750.00\n"
    )
    df = parse_statement_text(text)
    assert df is not None
    assert len(df) == 2
    assert df.iloc[0]["Description"] == "UPI-SWIGGY"
    assert df.iloc[0]["Debit"] == "250.00"
    assert df.iloc[0]["Credit"] == ""
    assert df.iloc[1]["Credit"] == "50000.00"
    assert df.iloc[1]["Debit"] == ""


def test_native_pdf_fixture_parses_via_text_fallback(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Force no camelot so we prove the text path works alone.
    monkeypatch.setenv("FINUNDERWRITE_ENABLE_CAMELOT_FALLBACK", "false")
    path = Path(__file__).resolve().parents[1] / "fixtures" / "sbi_native.pdf"
    profile = profile_file(path)
    result = NativePdfParser().parse(path, profile)
    assert len(result.dataframe) >= 2
    assert "Txn Date" in list(result.dataframe.columns) or "Date" in " ".join(
        str(c) for c in result.dataframe.columns
    )
