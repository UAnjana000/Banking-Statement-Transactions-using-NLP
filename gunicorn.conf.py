"""Gunicorn settings for ASGI FastAPI deployment."""

from __future__ import annotations

import os


bind = f"0.0.0.0:{os.getenv('PORT', '7860')}"
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.getenv("WEB_CONCURRENCY", "1"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
