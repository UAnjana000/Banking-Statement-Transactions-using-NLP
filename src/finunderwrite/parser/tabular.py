"""CSV and XLSX parser via pandas."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger

from finunderwrite.inventory.profiler import FileProfile
from finunderwrite.parser.base import ParseMetadata, Parser, ParseResult


class TabularParser(Parser):
    """Parse CSV/XLSX files using pandas."""

    name = "tabular"

    def can_parse(self, profile: FileProfile) -> bool:
        return profile.file_type in {"csv", "xlsx"}

    def parse(self, path: Path, profile: FileProfile | None = None) -> ParseResult:
        suffix = path.suffix.lower()
        try:
            if suffix == ".csv":
                df = pd.read_csv(path, dtype=str, keep_default_na=False)
            elif suffix in {".xlsx", ".xls"}:
                df = pd.read_excel(path, dtype=str)
                df = df.fillna("")
            else:
                msg = f"TabularParser cannot handle suffix: {suffix}"
                raise ValueError(msg)
        except Exception as exc:
            msg = f"Failed to read tabular file {path.name}: {exc}"
            logger.error(msg)
            raise ValueError(msg) from exc

        df.columns = [str(c).strip() for c in df.columns]
        if df.empty:
            msg = f"No rows found in {path.name}"
            raise ValueError(msg)

        return ParseResult(
            dataframe=df,
            metadata=ParseMetadata(
                source_path=path,
                parser_name=self.name,
                table_count=1,
            ),
        )
