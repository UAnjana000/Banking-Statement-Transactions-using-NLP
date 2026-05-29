"""Tests for inventory profiler."""

from __future__ import annotations

from pathlib import Path

import pytest

from finunderwrite.inventory.profiler import profile_file, profile_folder


def test_profile_sbi_csv(fixtures_dir: Path) -> None:
    path = fixtures_dir / "sbi_style.csv"
    profile = profile_file(path)
    assert profile.file_type == "csv"
    assert profile.has_text_layer is True
    assert profile.layout_hint == "tabular"
    assert profile.pdf_kind is None


def test_profile_canara_csv_detects_bank(fixtures_dir: Path) -> None:
    # Canara CSV content doesn't include bank name in file; bank may be None
    path = fixtures_dir / "canara_style.csv"
    profile = profile_file(path)
    assert profile.file_type == "csv"
    assert profile.detected_bank is None or profile.detected_bank == "Canara Bank"


def test_profile_folder_returns_all_supported(fixtures_dir: Path) -> None:
    profiles = profile_folder(fixtures_dir)
    names = {p.path.name for p in profiles}
    assert "sbi_style.csv" in names
    assert "canara_style.csv" in names


@pytest.mark.skipif(
    not (Path(__file__).resolve().parent.parent / "fixtures" / "sbi_native.pdf").exists(),
    reason="native PDF fixture not generated",
)
def test_profile_native_pdf(fixtures_dir: Path) -> None:
    pdf_path = fixtures_dir / "sbi_native.pdf"
    if not pdf_path.exists():
        pytest.skip("pdfplumber not available to validate native PDF")
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        pytest.skip("pdfplumber not installed")

    from tests.helpers.pdf_writer import write_text_pdf

    if not pdf_path.exists():
        write_text_pdf(pdf_path, ["State Bank of India", "Txn Date Description Debit Credit"])

    profile = profile_file(pdf_path)
    assert profile.file_type == "pdf"
    assert profile.pdf_kind == "native"
    assert profile.has_text_layer is True
    assert profile.detected_bank == "SBI"


def test_profile_scanned_pdf(fixtures_dir: Path) -> None:
    pdf_path = fixtures_dir / "scanned_blank.pdf"
    try:
        from PIL import Image, ImageDraw

        if not pdf_path.exists() or pdf_path.stat().st_size < 500:
            img = Image.new("RGB", (612, 792), color="white")
            draw = ImageDraw.Draw(img)
            draw.text((50, 50), "image only", fill="black")
            img.save(pdf_path, "PDF")
    except ImportError:
        pytest.skip("Pillow not installed")

    import importlib.util

    if importlib.util.find_spec("pdfplumber") is None:
        pytest.skip("pdfplumber not installed")

    profile = profile_file(pdf_path)
    assert profile.file_type == "pdf"
    assert profile.pdf_kind == "scanned"
    assert profile.has_text_layer is False
