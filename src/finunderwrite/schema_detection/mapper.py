"""Schema detection: map arbitrary columns to canonical fields."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from config.settings import Settings, get_settings
from config.yaml_loader import load_yaml
from loguru import logger
from pydantic import BaseModel, Field
from rapidfuzz import fuzz

CANONICAL_FIELDS = (
    "date",
    "description",
    "debit",
    "credit",
    "balance",
    "reference_number",
    "amount",
)

_DATE_PATTERNS = (
    re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"),
    re.compile(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}"),
)


class FieldMapping(BaseModel):
    canonical_field: str
    source_column: str
    confidence: float
    method: str


class ColumnMapping(BaseModel):
    mappings: list[FieldMapping] = Field(default_factory=list)
    unmapped_columns: list[str] = Field(default_factory=list)

    def get_column(self, field: str) -> str | None:
        for m in self.mappings:
            if m.canonical_field == field:
                return m.source_column
        return None

    def confidence_for(self, field: str) -> float:
        for m in self.mappings:
            if m.canonical_field == field:
                return m.confidence
        return 0.0


def load_synonyms(path: Path | None = None) -> dict[str, list[str]]:
    settings = get_settings()
    yaml_path = path or settings.column_synonyms_path
    if not yaml_path.exists():
        msg = f"Column synonyms file not found: {yaml_path}"
        raise FileNotFoundError(msg)
    raw = load_yaml(yaml_path)
    result: dict[str, list[str]] = {}
    for key, value in raw.items():
        if isinstance(value, list):
            result[key] = [str(v) for v in value]
        elif isinstance(value, str):
            result[key] = [value]
    return result


def detect_schema(
    df: pd.DataFrame,
    synonyms: dict[str, list[str]] | None = None,
    settings: Settings | None = None,
) -> ColumnMapping:
    """Detect column mapping using synonym, fuzzy, then type inference."""
    if df.empty:
        msg = "Cannot detect schema on empty DataFrame"
        raise ValueError(msg)

    settings = settings or get_settings()
    synonyms = synonyms or load_synonyms()
    columns = [str(c) for c in df.columns]
    used: set[str] = set()
    mappings: list[FieldMapping] = []

    for field in CANONICAL_FIELDS:
        match = _exact_or_synonym_match(field, columns, synonyms, used)
        if match:
            mappings.append(match)
            used.add(match.source_column)
            continue
        fuzzy = _fuzzy_match(field, columns, synonyms, used, settings.fuzzy_match_threshold)
        if fuzzy:
            mappings.append(fuzzy)
            used.add(fuzzy.source_column)

    # Type inference for remaining canonical fields
    for field in ("date", "balance", "debit", "credit", "amount"):
        if any(m.canonical_field == field for m in mappings):
            continue
        inferred = _type_inference(field, df, columns, used)
        if inferred:
            mappings.append(inferred)
            used.add(inferred.source_column)

    unmapped = [c for c in columns if c not in used]
    if unmapped:
        logger.warning("Unmapped columns (not dropped): {}", unmapped)

    return ColumnMapping(mappings=mappings, unmapped_columns=unmapped)


def _normalize_col(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _exact_or_synonym_match(
    field: str,
    columns: list[str],
    synonyms: dict[str, list[str]],
    used: set[str],
) -> FieldMapping | None:
    candidates = {_normalize_col(field)} | {_normalize_col(s) for s in synonyms.get(field, [])}
    for col in columns:
        if col in used:
            continue
        if _normalize_col(col) in candidates:
            return FieldMapping(
                canonical_field=field,
                source_column=col,
                confidence=1.0,
                method="exact",
            )
    return None


def _fuzzy_match(
    field: str,
    columns: list[str],
    synonyms: dict[str, list[str]],
    used: set[str],
    threshold: int,
) -> FieldMapping | None:
    targets = [field, *synonyms.get(field, [])]
    best_col: str | None = None
    best_score = 0.0
    for col in columns:
        if col in used:
            continue
        col_norm = _normalize_col(col)
        for target in targets:
            score = fuzz.token_sort_ratio(col_norm, _normalize_col(target))
            if score > best_score:
                best_score = score
                best_col = col
    if best_col and best_score >= threshold:
        return FieldMapping(
            canonical_field=field,
            source_column=best_col,
            confidence=round(best_score / 100.0, 3),
            method="fuzzy",
        )
    return None


def _type_inference(
    field: str,
    df: pd.DataFrame,
    columns: list[str],
    used: set[str],
) -> FieldMapping | None:
    for col in columns:
        if col in used:
            continue
        series = df[col].astype(str).str.strip()
        if field == "date" and _is_date_column(series):
            return FieldMapping(
                canonical_field=field,
                source_column=col,
                confidence=0.75,
                method="type_inference",
            )
        if field == "balance" and _is_balance_column(series):
            return FieldMapping(
                canonical_field=field,
                source_column=col,
                confidence=0.7,
                method="type_inference",
            )
        if field in {"debit", "credit", "amount"} and _is_amount_column(series):
            return FieldMapping(
                canonical_field=field,
                source_column=col,
                confidence=0.65,
                method="type_inference",
            )
    return None


def _is_date_column(series: pd.Series) -> bool:
    sample = series.head(20)
    hits = 0
    for val in sample:
        if not val or val.lower() in {"nan", "none"}:
            continue
        if any(p.search(val) for p in _DATE_PATTERNS):
            hits += 1
    return hits >= max(3, len(sample) // 3)


def _is_amount_column(series: pd.Series) -> bool:
    sample = series.head(20).str.replace(",", "", regex=False)
    hits = 0
    for val in sample:
        if not val or val.lower() in {"nan", "none", ""}:
            continue
        try:
            Decimal(val)
            hits += 1
        except InvalidOperation:
            continue
    return hits >= max(3, len(sample) // 3)


def _is_balance_column(series: pd.Series) -> bool:
    if not _is_amount_column(series):
        return False
    nums: list[Decimal] = []
    for val in series.head(30):
        val = str(val).replace(",", "").strip()
        if not val or val.lower() in {"nan", "none"}:
            continue
        try:
            nums.append(Decimal(val))
        except InvalidOperation:
            continue
    if len(nums) < 3:
        return False
    diffs = [abs(nums[i] - nums[i - 1]) for i in range(1, len(nums))]
    return sum(1 for d in diffs if d > 0) >= len(diffs) // 2
