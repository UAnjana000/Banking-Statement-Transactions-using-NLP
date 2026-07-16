"""Liveness endpoint for platform health checks (Hugging Face Spaces / local)."""

from __future__ import annotations

from config.settings import get_settings
from fastapi import APIRouter

from finunderwrite import __version__
from finunderwrite.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        max_upload_mb=settings.max_upload_mb,
    )
