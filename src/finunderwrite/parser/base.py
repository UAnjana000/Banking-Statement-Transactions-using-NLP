"""Parser ABC and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from finunderwrite.inventory.profiler import FileProfile


class ParseMetadata(BaseModel):
    """Metadata returned alongside a parsed DataFrame."""

    source_path: Path
    parser_name: str
    page_count: int | None = None
    table_count: int = 0
    extra: dict[str, Any] = Field(default_factory=dict)


class ParseResult(BaseModel):
    """Successful parse output."""

    model_config = {"arbitrary_types_allowed": True}

    dataframe: Any  # pd.DataFrame — typed loosely for pydantic
    metadata: ParseMetadata

    def df(self) -> pd.DataFrame:
        return self.dataframe


class ParseError(BaseModel):
    """Per-file parse failure."""

    source_path: Path
    parser_name: str
    message: str


class BatchParseResult(BaseModel):
    """Aggregate result for a batch of files."""

    model_config = {"arbitrary_types_allowed": True}

    results: list[ParseResult] = Field(default_factory=list)
    errors: list[ParseError] = Field(default_factory=list)


class Parser(ABC):
    """Abstract base for file parsers."""

    name: str = "base"

    @abstractmethod
    def parse(self, path: Path, profile: FileProfile | None = None) -> ParseResult:
        """Parse *path* into a raw table DataFrame."""

    def can_parse(self, profile: FileProfile) -> bool:
        return False
