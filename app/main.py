"""FastAPI application factory.

The factory builds the engine, creates the schema, and stashes the engine /
session factory / clock / extractor registry on ``app.state`` so dependencies can
reach them. Taking these as parameters lets tests build an app bound to an
isolated in-memory database and a deterministic clock with no global state.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.core.clock import Clock, SystemClock
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import build_engine, create_all, make_session_factory
from app.services.extraction import ExtractorRegistry, default_registry


def create_app(
    *,
    database_url: str | None = None,
    clock: Clock | None = None,
    registry: ExtractorRegistry | None = None,
) -> FastAPI:
    configure_logging()
    settings = get_settings()

    engine = build_engine(database_url or settings.database_url)
    create_all(engine)

    app = FastAPI(
        title="Support Memory Reliability Layer",
        version="0.1.0",
        description=(
            "Event-sourced memory for an AI support assistant: immutable events, "
            "extracted facts, an evidence graph, derived beliefs, and first-class "
            "contradiction / staleness / identity / idempotency handling."
        ),
    )
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.clock = clock or SystemClock()
    app.state.extractor_registry = registry or default_registry()

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    # Routers are imported lazily so importing app.main stays cheap.
    from app.api.routes import conflicts, context, explain, ingest

    app.include_router(ingest.router)
    app.include_router(context.router)
    app.include_router(explain.router)
    app.include_router(conflicts.router)
    return app


app = create_app()
