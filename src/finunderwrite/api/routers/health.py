"""Liveness endpoint (required for the Render health check)."""

from __future__ import annotations

from fastapi import APIRouter

from finunderwrite import __version__
from finunderwrite.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)
