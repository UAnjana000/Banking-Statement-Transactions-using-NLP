"""Universal parser dispatch and batch runner."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from finunderwrite.inventory.profiler import FileProfile, profile_file
from finunderwrite.parser.base import BatchParseResult, ParseError, Parser
from finunderwrite.parser.pdf_native import NativePdfParser
from finunderwrite.parser.tabular import TabularParser


def _all_parsers() -> list[Parser]:
    parsers: list[Parser] = [
        TabularParser(),
        NativePdfParser(),
    ]
    try:
        from finunderwrite.parser.pdf_scanned import ScannedPdfParser

        parsers.append(ScannedPdfParser())
    except ImportError as exc:
        logger.debug("ScannedPdfParser unavailable: {}", exc)
    return parsers


def get_parser(profile: FileProfile) -> Parser | None:
    for parser in _all_parsers():
        if parser.can_parse(profile):
            return parser
    return None


def parse_file(path: Path, profile: FileProfile | None = None) -> BatchParseResult:
    """Parse a single file; wraps result in BatchParseResult."""
    if profile is None:
        profile = profile_file(path)
    return parse_batch([profile])


def parse_batch(profiles: list[FileProfile]) -> BatchParseResult:
    """Parse multiple files; collect per-file errors without aborting the batch."""
    batch = BatchParseResult()
    for profile in profiles:
        parser = get_parser(profile)
        if parser is None:
            msg = f"No parser available for {profile.path.name} (type={profile.file_type})"
            logger.error(msg)
            batch.errors.append(
                ParseError(source_path=profile.path, parser_name="none", message=msg)
            )
            continue
        try:
            result = parser.parse(profile.path, profile)
            batch.results.append(result)
            logger.info("Parsed {} with {}", profile.path.name, parser.name)
        except Exception as exc:
            msg = str(exc)
            logger.error("Parse failed for {}: {}", profile.path.name, msg)
            batch.errors.append(
                ParseError(source_path=profile.path, parser_name=parser.name, message=msg)
            )
    return batch
