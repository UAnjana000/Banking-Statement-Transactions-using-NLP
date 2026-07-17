"""Tests for native PDF table coalescing helpers."""

from __future__ import annotations

import pandas as pd

from finunderwrite.parser.pdf_native import (
    _coalesce_compatible_frames,
    _ensure_unique_columns,
    _unique_column_names,
    camelot_fallback_enabled,
    max_sync_pdf_pages,
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


def test_camelot_fallback_disabled_on_render(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("FINUNDERWRITE_ENABLE_CAMELOT_FALLBACK", raising=False)
    monkeypatch.setenv("RENDER", "true")
    assert camelot_fallback_enabled() is False


def test_camelot_fallback_can_be_forced_on(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("FINUNDERWRITE_ENABLE_CAMELOT_FALLBACK", "true")
    assert camelot_fallback_enabled() is True


def test_max_sync_pdf_pages_defaults_low_on_render(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("FINUNDERWRITE_MAX_SYNC_PDF_PAGES", raising=False)
    monkeypatch.setenv("RENDER", "true")
    assert max_sync_pdf_pages() == 8
