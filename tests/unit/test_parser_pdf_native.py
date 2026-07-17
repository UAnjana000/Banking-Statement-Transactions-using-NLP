"""Tests for native PDF table coalescing helpers and camelot batching."""

from __future__ import annotations

import pandas as pd

from finunderwrite.parser.pdf_native import (
    _coalesce_compatible_frames,
    _ensure_unique_columns,
    _page_batches,
    _unique_column_names,
    camelot_batch_pages,
    camelot_fallback_enabled,
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


def test_page_batches() -> None:
    assert _page_batches(12, 5) == ["1-5", "6-10", "11-12"]
    assert _page_batches(3, 5) == ["1-3"]
    assert _page_batches(5, 5) == ["1-5"]
    assert _page_batches(0, 5) == []
    assert _page_batches(1, 1) == ["1-1"]


def test_camelot_batch_pages_default_and_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("FINUNDERWRITE_CAMELOT_BATCH_PAGES", raising=False)
    assert camelot_batch_pages() == 5
    monkeypatch.setenv("FINUNDERWRITE_CAMELOT_BATCH_PAGES", "3")
    assert camelot_batch_pages() == 3
