"""Request-ID middleware and a small in-process rate limiter."""

from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from pathlib import Path

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from finunderwrite.logging import set_request_id

_REQUEST_ID_HEADER = "X-Request-ID"
_DEBUG_SESSION_ID = "879ff3"
_DEBUG_LOG_PATH = Path(__file__).resolve().parents[4] / "debug-879ff3.log"


def _debug_log(
    *,
    run_id: str,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, object] | None = None,
) -> None:
    payload = {
        "sessionId": _DEBUG_SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
    }
    try:
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign/propagate a request id and log request start/end."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        started_at = time.perf_counter()
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
        set_request_id(request_id)
        request.state.request_id = request_id
        logger.info("--> {} {}", request.method, request.url.path)
        # region agent log
        _debug_log(
            run_id="render-502-investigation",
            hypothesis_id="H3",
            location="src/finunderwrite/api/middleware.py:dispatch",
            message="request entered middleware",
            data={"method": request.method, "path": request.url.path, "request_id": request_id},
        )
        # endregion
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            # region agent log
            _debug_log(
                run_id="render-502-investigation",
                hypothesis_id="H3",
                location="src/finunderwrite/api/middleware.py:dispatch",
                message="middleware observed exception from downstream",
                data={
                    "method": request.method,
                    "path": request.url.path,
                    "request_id": request_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
                },
            )
            # endregion
            raise
        response.headers[_REQUEST_ID_HEADER] = request_id
        # region agent log
        _debug_log(
            run_id="render-502-investigation",
            hypothesis_id="H5",
            location="src/finunderwrite/api/middleware.py:dispatch",
            message="request completed middleware",
            data={
                "method": request.method,
                "path": request.url.path,
                "request_id": request_id,
                "status_code": response.status_code,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        # endregion
        logger.info("<-- {} {} {}", request.method, request.url.path, response.status_code)
        return response


class RateLimiter:
    """Fixed-window per-key rate limiter (in-process)."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - self._window
        recent = [t for t in self._hits[key] if t >= window_start]
        recent.append(now)
        self._hits[key] = recent
        return len(recent) <= self._max
