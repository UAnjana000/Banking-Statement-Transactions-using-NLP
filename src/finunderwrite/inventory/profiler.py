"""Inventory / file profiler."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field

FileType = Literal["csv", "xlsx", "pdf"]
PdfKind = Literal["native", "scanned"]

_SUFFIX_MAP: dict[str, FileType] = {
    ".csv": "csv",
    ".xlsx": "xlsx",
    ".xls": "xlsx",
    ".pdf": "pdf",
}

# Heuristic bank detection — never assume; detect and log.
_BANK_KEYWORDS: dict[str, list[str]] = {
    "SBI": ["state bank of india", "sbi", "sbin"],
    "Canara Bank": ["canara bank", "canara"],
    "HDFC Bank": ["hdfc bank", "hdfc"],
    "ICICI Bank": ["icici bank", "icici"],
    "Axis Bank": ["axis bank", "axis"],
    "PNB": ["punjab national bank", "pnb"],
}


class FileProfile(BaseModel):
    """Profiling result for a single input file."""

    path: Path
    file_type: FileType
    pdf_kind: PdfKind | None = None
    detected_bank: str | None = None
    layout_hint: str | None = None
    has_text_layer: bool = False
    errors: list[str] = Field(default_factory=list)


def profile_folder(folder: Path) -> list[FileProfile]:
    """Scan *folder* and profile each supported file."""
    if not folder.exists():
        msg = f"Folder does not exist: {folder}"
        raise FileNotFoundError(msg)
    if not folder.is_dir():
        msg = f"Path is not a directory: {folder}"
        raise NotADirectoryError(msg)

    profiles: list[FileProfile] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in _SUFFIX_MAP:
            logger.debug("Skipping unsupported file: {}", path.name)
            continue
        try:
            profiles.append(profile_file(path))
        except Exception as exc:
            logger.error("Failed to profile {}: {}", path.name, exc)
            profiles.append(
                FileProfile(
                    path=path,
                    file_type=_SUFFIX_MAP[suffix],
                    errors=[str(exc)],
                )
            )
    return profiles


def profile_file(path: Path) -> FileProfile:
    """Profile a single file."""
    suffix = path.suffix.lower()
    if suffix not in _SUFFIX_MAP:
        msg = f"Unsupported file type: {path.suffix}"
        raise ValueError(msg)

    file_type = _SUFFIX_MAP[suffix]
    profile = FileProfile(path=path, file_type=file_type)

    if file_type == "pdf":
        _profile_pdf(path, profile)
    else:
        profile.has_text_layer = True
        profile.layout_hint = "tabular"
        _detect_bank_from_text(_read_text_sample(path), profile)

    return profile


def _profile_pdf(path: Path, profile: FileProfile) -> None:
    try:
        import pdfplumber
    except ImportError as exc:
        msg = "pdfplumber is required for PDF profiling"
        raise ImportError(msg) from exc

    text_chunks: list[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:3]:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_chunks.append(page_text)
    except Exception as exc:
        msg = f"Failed to open PDF {path.name}: {exc}"
        logger.error(msg)
        profile.errors.append(msg)
        profile.pdf_kind = "scanned"
        profile.has_text_layer = False
        profile.layout_hint = "unknown"
        return

    combined = "\n".join(text_chunks)
    non_trivial = len(combined.strip()) >= 20

    if non_trivial:
        profile.pdf_kind = "native"
        profile.has_text_layer = True
        profile.layout_hint = _infer_pdf_layout(combined)
    else:
        profile.pdf_kind = "scanned"
        profile.has_text_layer = False
        profile.layout_hint = "scanned_image"

    _detect_bank_from_text(combined, profile)


def _infer_pdf_layout(text: str) -> str:
    lower = text.lower()
    if "debit" in lower and "credit" in lower:
        return "dual_amount_columns"
    if "withdrawal" in lower or "deposit" in lower:
        return "withdrawal_deposit_columns"
    if "particulars" in lower or "narration" in lower:
        return "narration_table"
    return "generic_table"


def _read_text_sample(path: Path, max_bytes: int = 8192) -> str:
    try:
        raw = path.read_bytes()[:max_bytes]
        return raw.decode("utf-8", errors="ignore")
    except OSError as exc:
        logger.warning("Could not read sample from {}: {}", path.name, exc)
        return ""


def _detect_bank_from_text(text: str, profile: FileProfile) -> None:
    lower = text.lower()
    for bank, keywords in _BANK_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            profile.detected_bank = bank
            logger.info("Detected bank '{}' for {}", bank, profile.path.name)
            return
