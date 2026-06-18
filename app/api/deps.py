"""FastAPI dependency wiring.

Engine, session factory, clock, and extractor registry live on ``app.state``.
Sessions are request-scoped. The ingest service owns its (two-phase) commits; the
conflict PATCH route commits explicitly; read services never commit. FastAPI
caches sub-dependencies per request, so all services in one request share a session.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.services.conflict_service import ConflictService
from app.services.context_builder import ContextBuilder
from app.services.context_diff import ContextDiffService
from app.services.explainability import ExplainabilityService
from app.services.ingest_service import IngestService


def get_session(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_ingest_service(
    request: Request,
    session: Session = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> IngestService:
    return IngestService(session, clock, registry=request.app.state.extractor_registry)


def get_context_builder(
    session: Session = Depends(get_session), clock: Clock = Depends(get_clock)
) -> ContextBuilder:
    return ContextBuilder(session, clock)


def get_explainability(
    session: Session = Depends(get_session), clock: Clock = Depends(get_clock)
) -> ExplainabilityService:
    return ExplainabilityService(session, clock)


def get_conflict_service(session: Session = Depends(get_session)) -> ConflictService:
    return ConflictService(session)


def get_context_diff(
    session: Session = Depends(get_session), clock: Clock = Depends(get_clock)
) -> ContextDiffService:
    return ContextDiffService(session, clock)
