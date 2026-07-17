"""Render-compatible ASGI entry module for ``gunicorn app:app``."""

from __future__ import annotations

import json
import sys
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


_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
    _emit_debug_log(
        run_id="post-fix",
        hypothesis_id="H2",
        location="app.py:module",
        message="Inserted src into sys.path",
        data={"src_path": str(_SRC)},
    )

_emit_debug_log(
    run_id="post-fix",
    hypothesis_id="H1",
    location="app.py:module",
    message="Top-level app module loaded",
    data={"cwd": str(Path.cwd())},
)

from finunderwrite.api import app, create_app

_emit_debug_log(
    run_id="post-fix",
    hypothesis_id="H1",
    location="app.py:module",
    message="Imported finunderwrite.api successfully",
    data={"exports": ["app", "create_app"]},
)

__all__ = ["app", "create_app"]
