"""FastAPI application factory."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from config.settings import get_settings
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from finunderwrite import __version__
from finunderwrite.api.middleware import RequestIdMiddleware
from finunderwrite.api.routers import (
    features,
    health,
    profile,
    statements,
    synthetic,
    transactions,
)
from finunderwrite.logging import configure_logging, get_request_id

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
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


def create_app() -> FastAPI:
    settings = get_settings()
    # region agent log
    _debug_log(
        run_id="render-502-investigation",
        hypothesis_id="H1",
        location="src/finunderwrite/api/app.py:create_app",
        message="create_app entered",
        data={
            "static_dir": str(_STATIC_DIR),
            "static_dir_exists": _STATIC_DIR.is_dir(),
            "styles_css_exists": (_STATIC_DIR / "styles.css").is_file(),
        },
    )
    # endregion
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        from finunderwrite.persistence.database import init_db

        startup_started = time.perf_counter()
        # region agent log
        _debug_log(
            run_id="render-502-investigation",
            hypothesis_id="H4",
            location="src/finunderwrite/api/app.py:lifespan",
            message="lifespan startup begin",
            data={},
        )
        # endregion
        try:
            init_db(settings)
            # region agent log
            _debug_log(
                run_id="render-502-investigation",
                hypothesis_id="H4",
                location="src/finunderwrite/api/app.py:lifespan",
                message="lifespan startup db init success",
                data={"elapsed_ms": round((time.perf_counter() - startup_started) * 1000, 2)},
            )
            # endregion
        except Exception as exc:  # pragma: no cover - startup best-effort
            # region agent log
            _debug_log(
                run_id="render-502-investigation",
                hypothesis_id="H4",
                location="src/finunderwrite/api/app.py:lifespan",
                message="lifespan startup db init failed",
                data={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "elapsed_ms": round((time.perf_counter() - startup_started) * 1000, 2),
                },
            )
            # endregion
            logger.error("DB init failed on startup: {}", exc)
        yield

    app = FastAPI(
        title="FinUnderWrite",
        version=__version__,
        description="Bank-agnostic banking transaction intelligence API",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)

    app.include_router(health.router)
    app.include_router(statements.router)
    app.include_router(transactions.router)
    app.include_router(profile.router)
    app.include_router(features.router)
    app.include_router(synthetic.router)

    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
        # region agent log
        _debug_log(
            run_id="render-502-investigation",
            hypothesis_id="H1",
            location="src/finunderwrite/api/app.py:create_app",
            message="static mount enabled",
            data={
                "styles_css_exists": (_STATIC_DIR / "styles.css").is_file(),
                "index_html_exists": (_STATIC_DIR / "index.html").is_file(),
            },
        )
        # endregion

        @app.get("/", include_in_schema=False)
        async def ui_index() -> FileResponse:
            # region agent log
            _debug_log(
                run_id="render-502-investigation",
                hypothesis_id="H2",
                location="src/finunderwrite/api/app.py:ui_index",
                message="ui index requested",
                data={"index_html_exists": (_STATIC_DIR / "index.html").is_file()},
            )
            # endregion
            return FileResponse(_STATIC_DIR / "index.html")
    else:
        # region agent log
        _debug_log(
            run_id="render-502-investigation",
            hypothesis_id="H1",
            location="src/finunderwrite/api/app.py:create_app",
            message="static mount skipped",
            data={"reason": "static_dir_missing", "static_dir": str(_STATIC_DIR)},
        )
        # endregion

    _register_exception_handlers(app)

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "http_error",
                "detail": str(exc.detail),
                "request_id": get_request_id(),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "detail": exc.errors(),
                "request_id": get_request_id(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exc_handler(request: Request, exc: Exception) -> JSONResponse:
        # BaseHTTPMiddleware can surface HTTPException as a bare Exception.
        if isinstance(exc, StarletteHTTPException):
            return await http_exc_handler(request, exc)
        logger.exception("Unhandled error")
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": "An unexpected error occurred",
                "request_id": get_request_id(),
            },
        )


app = create_app()
