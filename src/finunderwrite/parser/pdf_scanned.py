"""Scanned PDF parser: pdf2image -> tesseract -> row reconstruction."""

from __future__ import annotations

from pathlib import Path

from config.settings import get_settings
from loguru import logger

from finunderwrite.inventory.profiler import FileProfile
from finunderwrite.parser.base import ParseMetadata, Parser, ParseResult
from finunderwrite.parser.ocr.table_reconstruction import reconstruct_table_from_ocr
from finunderwrite.parser.ocr.tesseract_wrapper import ocr_pdf_to_lines


class ScannedPdfParser(Parser):
    """OCR-based parser for scanned/image PDFs."""

    name = "pdf_scanned"

    def can_parse(self, profile: FileProfile) -> bool:
        return profile.file_type == "pdf" and profile.pdf_kind == "scanned"

    def parse(self, path: Path, profile: FileProfile | None = None) -> ParseResult:
        settings = get_settings()
        try:
            lines = ocr_pdf_to_lines(path, settings)
        except Exception as exc:
            msg = f"OCR failed on {path.name}: {exc}"
            logger.error(msg)
            raise ValueError(msg) from exc

        if not lines:
            msg = f"OCR returned no text for {path.name}"
            raise ValueError(msg)

        df = reconstruct_table_from_ocr(lines)
        if df.empty:
            msg = f"Could not reconstruct table from OCR for {path.name}"
            raise ValueError(msg)

        return ParseResult(
            dataframe=df,
            metadata=ParseMetadata(
                source_path=path,
                parser_name=self.name,
                table_count=1,
                extra={"ocr_line_count": len(lines)},
            ),
        )
