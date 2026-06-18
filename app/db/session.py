"""Engine and session construction.

Kept framework-agnostic (no FastAPI imports) so the same helpers serve the API,
the test-suite, and the CLI scripts. Two SQLite-specific concerns are handled:
foreign-key enforcement (off by default in SQLite) and using a ``StaticPool`` for
in-memory databases so every connection sees the same schema/data.
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base


def build_engine(url: str | None = None, *, echo: bool | None = None) -> Engine:
    settings = get_settings()
    url = url or settings.database_url
    echo = settings.sql_echo if echo is None else echo

    connect_args: dict = {}
    engine_kwargs: dict = {"echo": echo, "future": True}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # In-memory DBs must share a single connection or each session gets a
        # fresh, empty database.
        if url in ("sqlite://", "sqlite:///:memory:"):
            engine_kwargs["poolclass"] = StaticPool

    engine = create_engine(url, connect_args=connect_args, **engine_kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_connection, _record):  # pragma: no cover - trivial
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_all(engine: Engine) -> None:
    # Importing models registers them on Base.metadata before create_all.
    from app.db import models  # noqa: F401

    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False keeps ORM objects usable after commit, which the
    # service layer relies on when returning results from the ingest pipeline.
    return sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True, class_=Session
    )
