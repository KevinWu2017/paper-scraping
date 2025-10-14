from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None


def _build_engine(database_url: str) -> Any:
    connect_args: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = max(1, settings.sqlite_busy_timeout_seconds)
    engine = create_engine(database_url, future=True, echo=False, connect_args=connect_args)

    if database_url.startswith("sqlite"):
        _configure_sqlite_engine(engine)

    return engine


def _configure_sqlite_engine(engine: Any) -> None:
    journal_mode = settings.sqlite_journal_mode
    busy_timeout_ms = max(1, settings.sqlite_busy_timeout_seconds) * 1000

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-redef]
        cursor = dbapi_connection.cursor()
        try:
            if journal_mode:
                cursor.execute(f"PRAGMA journal_mode={journal_mode}")
            cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        finally:
            cursor.close()


def configure_engine(database_url: str | None = None) -> None:
    global _engine, _SessionLocal
    database_url = database_url or settings.database_url
    _engine = _build_engine(database_url)
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False, future=True)


configure_engine()


def get_session() -> Generator:
    if _SessionLocal is None:
        configure_engine()
    session = _SessionLocal()  # type: ignore[misc]
    try:
        yield session
    finally:
        session.close()


def get_engine():
    if _engine is None:
        configure_engine()
    return _engine


def init_db() -> None:
    from . import models  # noqa: F401 -- ensure models are registered

    engine = get_engine()
    if engine is None:  # pragma: no cover - defensive guard
        raise RuntimeError("Database engine is not configured")
    Base.metadata.create_all(bind=engine)
    _ensure_schema()


def _ensure_schema() -> None:
    engine = get_engine()
    if engine is None:  # safety guard for typing
        return
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("papers")}
    if "author_affiliations" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE papers ADD COLUMN author_affiliations TEXT"))


def create_session() -> Session:
    if _SessionLocal is None:
        configure_engine()
    return _SessionLocal()  # type: ignore[return-value]
