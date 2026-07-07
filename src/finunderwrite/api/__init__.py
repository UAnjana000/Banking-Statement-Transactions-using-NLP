"""FastAPI service (lightweight serving runtime; no torch/sdv)."""

from finunderwrite.api.app import app, create_app

__all__ = ["app", "create_app"]
