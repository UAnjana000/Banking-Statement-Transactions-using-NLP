"""Tests for tabular parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from finunderwrite.inventory.profiler import profile_file
from finunderwrite.parser.tabular import TabularParser


def test_tabular_parser_csv(fixtures_dir: Path) -> None:
    path = fixtures_dir / "sbi_style.csv"
    profile = profile_file(path)
    parser = TabularParser()
    assert parser.can_parse(profile)

    result = parser.parse(path, profile)
    df = result.df()
    assert len(df) == 3
    assert "Txn Date" in df.columns


def test_tabular_parser_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_text("Date,Amount\n", encoding="utf-8")
    profile = profile_file(empty)
    parser = TabularParser()
    with pytest.raises(ValueError, match="No rows"):
        parser.parse(empty, profile)
