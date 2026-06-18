"""Shared fixtures. Every test uses a fresh in-memory DB and a fixed clock."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.clock import FixedClock
from app.db.session import build_engine, create_all, make_session_factory
from app.domain.events import MemoryEvent
from app.services.ingest_service import IngestService

BASE_TIME = datetime(2026, 6, 18, tzinfo=timezone.utc)
SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed_events.json"


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(BASE_TIME)


@pytest.fixture
def engine():
    eng = build_engine("sqlite://")
    create_all(eng)
    return eng


@pytest.fixture
def session_factory(engine):
    return make_session_factory(engine)


@pytest.fixture
def session(session_factory):
    sess = session_factory()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture
def ingest(session, clock) -> IngestService:
    return IngestService(session, clock)


@pytest.fixture
def seed_events() -> list[dict]:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def loaded(ingest, seed_events):
    """Ingest the exact 20-event assignment dataset; returns the results."""
    return [ingest.ingest(MemoryEvent(**e)) for e in seed_events]


@pytest.fixture
def app(clock):
    from app.main import create_app

    return create_app(database_url="sqlite://", clock=clock)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seeded_client(client, seed_events):
    for event in seed_events:
        client.post("/v1/events:ingest", json=event)
    return client
