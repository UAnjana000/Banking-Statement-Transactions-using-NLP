"""FastAPI application factory."""

from __future__ import annotations

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


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        from finunderwrite.persistence.database import init_db

        try:
            init_db(settings)
        except Exception as exc:  # pragma: no cover - startup best-effort
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

        @app.get("/", include_in_schema=False)
        async def ui_index() -> FileResponse:
            return FileResponse(_STATIC_DIR / "index.html")

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
