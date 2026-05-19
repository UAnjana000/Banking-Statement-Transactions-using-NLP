"""Native PDF parser: pdfplumber with camelot fallback."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from loguru import logger

from finunderwrite.inventory.profiler import FileProfile
from finunderwrite.parser.base import ParseMetadata, Parser, ParseResult

_AMOUNT_RE = re.compile(r"^-?\d[\d,]*\.?\d*$")


class NativePdfParser(Parser):
    """Extract tables from text-layer PDFs."""

    name = "pdf_native"

    def can_parse(self, profile: FileProfile) -> bool:
        return profile.file_type == "pdf" and profile.pdf_kind == "native"

    def parse(self, path: Path, profile: FileProfile | None = None) -> ParseResult:
        try:
            import pdfplumber
        except ImportError as exc:
            msg = "pdfplumber is required for native PDF parsing"
            raise ImportError(msg) from exc

        frames: list[pd.DataFrame] = []
        page_count = 0
        header: list[str] | None = None

        try:
            with pdfplumber.open(path) as pdf:
                page_count = len(pdf.pages)
                for page in pdf.pages:
                    tables = page.extract_tables() or []
                    for table in tables:
                        if not table or len(table) < 2:
                            continue
                        df = _table_to_dataframe(table)
                        if df is None or df.empty:
                            continue
                        if header is None:
                            header = list(df.columns)
                            frames.append(df)
                        else:
                            df = _align_to_header(df, header)
                            if not df.empty:
                                frames.append(df)
        except Exception as exc:
            msg = f"pdfplumber failed on {path.name}: {exc}"
            logger.warning(msg)

        if not frames:
            frames = self._camelot_fallback(path)

        if not frames:
            msg = f"No tables extracted from native PDF: {path.name}"
            raise ValueError(msg)

        combined = pd.concat(frames, ignore_index=True)
        combined = _normalize_signed_amount_column(combined)

        return ParseResult(
            dataframe=combined,
            metadata=ParseMetadata(
                source_path=path,
                parser_name=self.name,
                page_count=page_count,
                table_count=len(frames),
            ),
        )

    def _camelot_fallback(self, path: Path) -> list[pd.DataFrame]:
        try:
            import camelot
        except ImportError:
            logger.debug("camelot not available for fallback")
            return []

        frames: list[pd.DataFrame] = []
        for flavor in ("lattice", "stream"):
            try:
                tables = camelot.read_pdf(str(path), pages="all", flavor=flavor)
            except Exception as exc:
                logger.debug("camelot {} failed on {}: {}", flavor, path.name, exc)
                continue
            for table in tables:
                df = table.df
                if df.shape[0] >= 2:
                    df.columns = df.iloc[0]
                    df = df.iloc[1:].reset_index(drop=True)
                    frames.append(df)
            if frames:
                logger.info(
                    "camelot ({}) extracted {} table(s) from {}",
                    flavor,
                    len(frames),
                    path.name,
                )
                break
        return frames


def _table_to_dataframe(table: list[list[str | None]]) -> pd.DataFrame | None:
    cleaned: list[list[str]] = []
    for row in table:
        cleaned.append([str(cell or "").strip() for cell in row])
    if len(cleaned) < 2:
        return None
    header = cleaned[0]
    rows = cleaned[1:]
    if not any(header):
        return None
    df = pd.DataFrame(rows, columns=header)
    return df.replace("", pd.NA).dropna(how="all")


def _align_to_header(df: pd.DataFrame, header: list[str]) -> pd.DataFrame:
    """Align continuation pages that lack repeated headers."""
    cols = [str(c).strip() for c in df.columns]
    first_row = df.iloc[0].astype(str).tolist() if not df.empty else []
    if _looks_like_header_row(first_row, header):
        df = df.iloc[1:].reset_index(drop=True)
        cols = first_row

    if len(cols) == len(header):
        df.columns = header
        return df.replace("", pd.NA).dropna(how="all")

    # Pad or trim to match header width
    if len(cols) < len(header):
        for i in range(len(cols), len(header)):
            df[f"_pad_{i}"] = pd.NA
        df.columns = header
    else:
        df = df.iloc[:, : len(header)]
        df.columns = header
    return df.replace("", pd.NA).dropna(how="all")


def _looks_like_header_row(row: list[str], header: list[str]) -> bool:
    row_lower = [r.lower().strip() for r in row]
    header_lower = [h.lower().strip() for h in header]
    matches = sum(1 for a, b in zip(row_lower, header_lower, strict=False) if a == b)
    return matches >= max(2, len(header) // 2)


def _normalize_signed_amount_column(df: pd.DataFrame) -> pd.DataFrame:
    """Detect a single signed amount column and annotate for downstream split."""
    lower_cols = {str(c).lower(): c for c in df.columns}
    amount_col = None
    for key in ("amount", "txn amount", "transaction amount", "signed amount"):
        if key in lower_cols:
            amount_col = lower_cols[key]
            break

    if amount_col is None:
        for col in df.columns:
            series = df[col].astype(str).str.strip()
            numeric = series.str.replace(",", "", regex=False).str.match(_AMOUNT_RE)
            if numeric.mean() > 0.6 and series.str.contains(r"^-").mean() > 0.1:
                amount_col = col
                break

    if amount_col is not None:
        df = df.copy()
        df.attrs["signed_amount_column"] = str(amount_col)
    return df
