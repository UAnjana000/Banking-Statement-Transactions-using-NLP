"""Tesseract OCR wrapper for PDF pages."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import pytesseract
from config.settings import Settings
from loguru import logger
from pdf2image import convert_from_path


@dataclass(frozen=True)
class OcrLine:
    text: str
    x: float
    y: float
    width: float
    height: float
    page: int


def _configure_tesseract(settings: Settings) -> None:
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        return
    if shutil.which("tesseract") is None:
        msg = (
            "Tesseract not found on PATH. Install tesseract-ocr or set "
            "FINUNDERWRITE_TESSERACT_CMD in .env"
        )
        raise RuntimeError(msg)


def ocr_pdf_to_lines(path: Path, settings: Settings) -> list[OcrLine]:
    """Convert PDF pages to images and run Tesseract; return positioned lines."""
    _configure_tesseract(settings)

    poppler = settings.poppler_path
    try:
        if poppler:
            images = convert_from_path(str(path), poppler_path=poppler)
        else:
            images = convert_from_path(str(path))
    except Exception as exc:
        msg = f"pdf2image/Poppler failed: {exc}"
        raise RuntimeError(msg) from exc

    lines: list[OcrLine] = []
    for page_idx, image in enumerate(images, start=1):
        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except Exception as exc:
            logger.warning("Tesseract failed on page {} of {}: {}", page_idx, path.name, exc)
            continue

        n = len(data["text"])
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            conf = float(data["conf"][i])
            if conf < 0:
                continue
            lines.append(
                OcrLine(
                    text=text,
                    x=float(data["left"][i]),
                    y=float(data["top"][i]),
                    width=float(data["width"][i]),
                    height=float(data["height"][i]),
                    page=page_idx,
                )
            )
    return lines
