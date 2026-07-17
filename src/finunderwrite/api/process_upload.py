"""Isolate heavy statement parsing so host OOMs do not kill the web worker."""

from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
from typing import Any

from loguru import logger

from finunderwrite.inventory.profiler import FileProfile


def _isolate_enabled() -> bool:
    """Opt-in only: spawning a second Python process can worsen 512MB OOM."""
    explicit = os.getenv("FINUNDERWRITE_ISOLATE_PDF_PARSE")
    if explicit is None:
        return False
    return explicit.strip().lower() in {"1", "true", "yes", "on"}


def _parse_timeout_seconds() -> int:
    raw = os.getenv("FINUNDERWRITE_PDF_PARSE_TIMEOUT_SECONDS", "90")
    try:
        return max(15, int(raw))
    except ValueError:
        return 90


def _worker(path_str: str, profile_payload: dict[str, Any], queue: mp.Queue) -> None:  # type: ignore[type-arg]
    """Child entrypoint: parse + enrich, return plain dict records."""
    try:
        from finunderwrite.api.pipeline import (
            enrich_transactions,
            parse_and_normalize,
            transaction_to_record,
        )

        path = Path(path_str)
        profile = FileProfile.model_validate(profile_payload)
        transactions = parse_and_normalize(path, profile)
        transactions = enrich_transactions(transactions)
        records = [transaction_to_record(t) for t in transactions]
        queue.put(
            {
                "ok": True,
                "records": records,
                "file_type": profile.file_type,
                "pdf_kind": profile.pdf_kind,
            }
        )
    except Exception as exc:  # pragma: no cover - defensive child boundary
        queue.put(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )


def process_statement_file(
    path: Path,
    profile: FileProfile,
) -> tuple[list[dict[str, Any]], str, str | None]:
    """Parse/enrich a statement. Optionally run PDF work in a child process."""
    if profile.file_type != "pdf" or not _isolate_enabled():
        from finunderwrite.api.pipeline import (
            enrich_transactions,
            parse_and_normalize,
            transaction_to_record,
        )

        transactions = parse_and_normalize(path, profile)
        transactions = enrich_transactions(transactions)
        records = [transaction_to_record(t) for t in transactions]
        return records, profile.file_type, profile.pdf_kind

    timeout = _parse_timeout_seconds()
    logger.info(
        "Parsing PDF {} in isolated process (timeout={}s)",
        path.name,
        timeout,
    )
    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()  # type: ignore[type-arg]
    proc = ctx.Process(
        target=_worker,
        args=(str(path), profile.model_dump(mode="json"), queue),
        daemon=True,
    )
    proc.start()
    proc.join(timeout=timeout)

    if proc.is_alive():
        proc.terminate()
        proc.join(5)
        msg = (
            f"PDF processing timed out after {timeout}s. "
            "Try a smaller statement or CSV/XLSX export."
        )
        raise TimeoutError(msg)

    if proc.exitcode not in (0, None) and queue.empty():
        msg = (
            "PDF processing was killed (likely out of memory on this host). "
            "Try a shorter statement, CSV/XLSX export, or a larger instance."
        )
        raise MemoryError(msg)

    try:
        payload = queue.get_nowait()
    except Exception as exc:
        msg = "PDF processing failed without a result"
        raise RuntimeError(msg) from exc

    if not payload.get("ok"):
        error = payload.get("error") or "PDF processing failed"
        error_type = payload.get("error_type") or "Error"
        if error_type == "ValueError":
            raise ValueError(error)
        raise RuntimeError(f"{error_type}: {error}")

    records = list(payload.get("records") or [])
    file_type = str(payload.get("file_type") or profile.file_type)
    pdf_kind = payload.get("pdf_kind")
    return records, file_type, pdf_kind if isinstance(pdf_kind, str) else None
