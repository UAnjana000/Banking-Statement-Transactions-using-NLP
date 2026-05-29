"""Shared pytest fixtures and synthetic statement generators."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    return FIXTURES_DIR


@pytest.fixture(scope="session", autouse=True)
def ensure_synthetic_fixtures(fixtures_dir: Path) -> None:
    """Generate synthetic fixtures once per test session."""
    from tests.helpers.pdf_writer import write_text_pdf

    sbi_csv = fixtures_dir / "sbi_style.csv"
    if not sbi_csv.exists():
        sbi_csv.write_text(
            "Txn Date,Description,Debit,Credit,Balance\n"
            "15/01/2025,UPI-SWIGGY,250.00,,4750.00\n"
            "16/01/2025,NEFT-SALARY,,50000.00,54750.00\n"
            "17/01/2025,ATM-WITHDRAWAL,2000.00,,52750.00\n",
            encoding="utf-8",
        )

    canara_csv = fixtures_dir / "canara_style.csv"
    if not canara_csv.exists():
        canara_csv.write_text(
            "Value Date,Particulars,Withdrawal,Deposit,Closing Balance\n"
            "2025-01-10,POS-GROCERY,1200.50,,8800.50\n"
            "2025-01-11,IMPS-TRANSFER,500.00,,8300.50\n"
            "2025-01-12,SALARY CREDIT,,45000.00,53300.50\n",
            encoding="utf-8",
        )

    signed_csv = fixtures_dir / "signed_amount.csv"
    if not signed_csv.exists():
        signed_csv.write_text(
            "Transaction Date,Narration,Amount,Balance\n"
            "01/02/2025,UPI-TEA,-45.00,9955.00\n"
            "02/02/2025,NEFT-REFUND,1200.00,11155.00\n",
            encoding="utf-8",
        )

    sbi_pdf = fixtures_dir / "sbi_native.pdf"
    if not sbi_pdf.exists():
        write_text_pdf(
            sbi_pdf,
            [
                "State Bank of India - Synthetic Statement",
                "Txn Date  Description  Debit  Credit  Balance",
                "15/01/2025  UPI-SWIGGY  250.00    4750.00",
                "16/01/2025  NEFT-SALARY    50000.00  54750.00",
            ],
            title="SBI Synthetic",
        )

    scanned_pdf = fixtures_dir / "scanned_blank.pdf"
    if not scanned_pdf.exists():
        try:
            from PIL import Image, ImageDraw

            img = Image.new("RGB", (612, 792), color="white")
            draw = ImageDraw.Draw(img)
            draw.text((50, 50), "Canara Bank Synthetic (image only)", fill="black")
            img.save(scanned_pdf, "PDF")
        except Exception:
            scanned_pdf.write_bytes(b"%PDF-1.4 minimal placeholder")


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """Provide a Settings pointing at a temp sqlite DB and temp model path.

    Patches the cached settings singleton, resets the DB engine, initializes
    the schema, and clears merchant module caches so each test is isolated.
    """
    import importlib

    from config import settings as settings_mod

    from finunderwrite.persistence import database

    categorize_mod = importlib.import_module("finunderwrite.merchant.categorize")
    extract_mod = importlib.import_module("finunderwrite.merchant.extract")

    db_file = tmp_path / "test.sqlite3"
    settings = settings_mod.Settings(
        database_url=f"sqlite:///{db_file.as_posix()}",
        categorizer_model_path=tmp_path / "categorizer.joblib",
        enrichment_rate_limit_per_sec=1000.0,
        enrichment_max_attempts=2,
        respect_robots=False,
    )
    monkeypatch.setattr(settings_mod, "_settings", settings)
    extract_mod._default_extractor.cache_clear()
    categorize_mod._default_categorizer.cache_clear()

    database.reset_engine()
    database.init_db(settings)
    try:
        yield settings
    finally:
        database.reset_engine()
        extract_mod._default_extractor.cache_clear()
        categorize_mod._default_categorizer.cache_clear()


def tesseract_available() -> bool:
    from config.settings import get_settings

    settings = get_settings()
    if settings.tesseract_cmd:
        return Path(settings.tesseract_cmd).exists()
    return shutil.which("tesseract") is not None


def poppler_available() -> bool:
    from config.settings import get_settings

    settings = get_settings()
    if settings.poppler_path:
        return Path(settings.poppler_path).exists()
    return shutil.which("pdftoppm") is not None
