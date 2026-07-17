"""Render-compatible ASGI entry module for ``gunicorn app:app``."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from finunderwrite.api import app, create_app

__all__ = ["app", "create_app"]
