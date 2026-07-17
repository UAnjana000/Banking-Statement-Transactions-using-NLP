"""Gunicorn settings for ASGI FastAPI deployment."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _emit_debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "508052",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with Path("debug-508052.log").open("a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass
    # endregion


bind = f"0.0.0.0:{os.getenv('PORT', '7860')}"
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.getenv("WEB_CONCURRENCY", "1"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))

_emit_debug_log(
    run_id="post-fix",
    hypothesis_id="H4",
    location="gunicorn.conf.py:module",
    message="Gunicorn ASGI config loaded",
    data={
        "bind": bind,
        "worker_class": worker_class,
        "workers": workers,
        "timeout": timeout,
    },
)
