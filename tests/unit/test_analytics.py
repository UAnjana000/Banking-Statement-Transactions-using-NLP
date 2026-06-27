"""Tests for the DuckDB read-only analytics helper."""

from __future__ import annotations

from pathlib import Path

from finunderwrite.persistence.analytics import read_csv, summarize


def _write_csv(path: Path) -> None:
    path.write_text("a,b\n1,10\n2,20\n3,30\n", encoding="utf-8")


def test_read_csv(tmp_path: Path) -> None:
    csv = tmp_path / "data.csv"
    _write_csv(csv)
    df = read_csv(csv)
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 3


def test_summarize(tmp_path: Path) -> None:
    csv = tmp_path / "data.csv"
    _write_csv(csv)
    summary = summarize(csv)
    assert summary["rows"] == 3
    assert summary["means"]["a"] == 2.0
    assert summary["means"]["b"] == 20.0
