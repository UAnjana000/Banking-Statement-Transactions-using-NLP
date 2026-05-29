"""Structured loguru logging with request-id propagation."""

from __future__ import annotations

import sys
from contextvars import ContextVar
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Record

# Propagates the current request id into every log record within a request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def _patch(record: Record) -> None:
    record["extra"].setdefault("request_id", request_id_var.get())


def configure_logging(level: str = "INFO") -> None:
    """Set up loguru with a single stderr sink that includes the request id."""
    logger.remove()
    logger.configure(patcher=_patch)
    logger.add(
        sys.stderr,
        level=level.upper(),
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "req=<cyan>{extra[request_id]}</cyan> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        enqueue=False,
    )


def set_request_id(request_id: str) -> None:
    request_id_var.set(request_id)


def get_request_id() -> str:
    return request_id_var.get()
