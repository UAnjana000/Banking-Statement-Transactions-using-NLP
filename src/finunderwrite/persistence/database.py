"""SQLAlchemy engine/session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from config.settings import Settings, get_settings
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all finunderwrite ORM models."""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine(settings: Settings | None = None) -> Engine:
    """Return a process-wide engine, creating it on first use."""
    global _engine, _session_factory
    settings = settings or get_settings()
    if _engine is None:
        url = settings.resolved_database_url
        if url.startswith("sqlite:///"):
            db_path = url.removeprefix("sqlite:///")
            if db_path and db_path != ":memory:":
                from pathlib import Path

                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, future=True)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db(settings: Settings | None = None) -> Engine:
    """Create all tables. Safe to call repeatedly."""
    engine = get_engine(settings)
    # Import models so they register on Base.metadata before create_all.
    from finunderwrite.persistence import models  # noqa: F401

    Base.metadata.create_all(engine)
    return engine


@contextmanager
def get_session(settings: Settings | None = None) -> Iterator[Session]:
    """Context-managed session with commit/rollback handling."""
    if _session_factory is None:
        get_engine(settings)
    assert _session_factory is not None
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Dispose the current engine (primarily for tests)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
