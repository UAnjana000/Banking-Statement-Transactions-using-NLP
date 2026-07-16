"""Statement upload + parse endpoint."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from config.settings import get_settings
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

from finunderwrite.api.pipeline import (
    enrich_transactions,
    parse_and_normalize,
    transaction_to_record,
)
from finunderwrite.api.schemas import StatementUploadResponse
from finunderwrite.inventory.profiler import profile_file
from finunderwrite.persistence import repository

router = APIRouter(tags=["statements"])

_ALLOWED_SUFFIXES = {".csv", ".xlsx", ".xls", ".pdf"}


def _format_upload_limit(max_bytes: int) -> str:
    mb = max_bytes / (1024 * 1024)
    if mb >= 1:
        text = f"{mb:.0f}" if mb == int(mb) else f"{mb:.1f}"
        return f"{text} MB"
    return f"{max_bytes} bytes"


@router.post("/statements", response_model=StatementUploadResponse)
async def upload_statement(
    file: UploadFile = File(...),
    customer_id: str = Form("default"),
) -> StatementUploadResponse | JSONResponse:
    settings = get_settings()
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds limit of {_format_upload_limit(settings.max_upload_bytes)}",
        )

    fd, tmp_name = tempfile.mkstemp(prefix=f"finuw_{customer_id}_", suffix=suffix)
    os.close(fd)
    tmp_path = Path(tmp_name)
    tmp_path.write_bytes(content)

    try:
        profile = profile_file(tmp_path)

        # Scanned PDFs are NOT OCR'd synchronously (would time out on a free instance).
        if profile.file_type == "pdf" and profile.pdf_kind == "scanned":
            return JSONResponse(
                status_code=202,
                content={
                    "status": "accepted",
                    "customer_id": customer_id,
                    "filename": filename,
                    "file_type": profile.file_type,
                    "pdf_kind": profile.pdf_kind,
                    "transactions_ingested": 0,
                    "note": (
                        "Scanned PDF queued for offline OCR batch; "
                        "OCR is not run synchronously on the serving instance."
                    ),
                },
            )

        transactions = parse_and_normalize(tmp_path, profile)
        transactions = enrich_transactions(transactions)
        records = [transaction_to_record(t) for t in transactions]
        ingested = repository.save_transactions(customer_id, records)

        return StatementUploadResponse(
            status="processed",
            customer_id=customer_id,
            filename=filename,
            file_type=profile.file_type,
            pdf_kind=profile.pdf_kind,
            transactions_ingested=ingested,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Statement processing failed")
        raise HTTPException(status_code=500, detail="Statement processing failed") from exc
    finally:
        # Parsers (camelot/pdfplumber) may still hold the file on Windows.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not delete temp upload {}: {}", tmp_path, exc)
