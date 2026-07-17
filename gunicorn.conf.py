"""Gunicorn settings for ASGI FastAPI deployment."""

from __future__ import annotations

import os

bind = f"0.0.0.0:{os.getenv('PORT', '7860')}"
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.getenv("WEB_CONCURRENCY", "1"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
# Keep a single worker on free-tier hosts; avoid preloading large PDF stacks.
preload_app = False
