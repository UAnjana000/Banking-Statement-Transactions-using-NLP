"""Request-ID middleware and a small in-process rate limiter."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from finunderwrite.logging import set_request_id

_REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign/propagate a request id and log request start/end."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
        set_request_id(request_id)
        request.state.request_id = request_id
        logger.info("--> {} {}", request.method, request.url.path)
        response: Response = await call_next(request)
        response.headers[_REQUEST_ID_HEADER] = request_id
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
