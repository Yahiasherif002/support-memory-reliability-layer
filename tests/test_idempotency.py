"""Idempotency: replay returns the same logical result; key-collision is a conflict."""

from __future__ import annotations

from app.domain.enums import DedupStatus
from app.domain.events import MemoryEvent

EVENT = {
    "event_id": "evt-a", "idempotency_key": "idem-a", "occurred_at": "2026-04-01T09:00:00Z",
    "source": "crm", "actor": "system", "entity_type": "account", "entity_id": "acct_x",
    "related_entity_ids": [], "reliability": "medium",
    "text": "Plan recorded as Starter.", "payload": {"plan": "Starter"},
}


def test_replay_returns_same_logical_result(ingest, session):
    first = ingest.ingest(MemoryEvent(**EVENT))
    second = ingest.ingest(MemoryEvent(**EVENT))
    assert first.dedup_status == DedupStatus.NEW and first.processed and first.facts_created >= 1
    assert second.dedup_status == DedupStatus.DUPLICATE_REPLAY
    assert second.processed == first.processed
    assert second.entity_id == first.entity_id
    assert second.facts_created == first.facts_created
    # No duplicate facts created on replay.
    from app.db.repositories import FactRepository
    assert len(FactRepository(session).list_for_entity("acct_x")) == first.facts_created


def test_same_key_different_payload_is_conflict(ingest, seed_events):
    by_id = {e["event_id"]: e for e in seed_events}
    r8 = ingest.ingest(MemoryEvent(**by_id["evt-1008"]))   # idem-1008, NEW
    r9 = ingest.ingest(MemoryEvent(**by_id["evt-1009"]))   # idem-1008 again, different body
    assert r8.dedup_status == DedupStatus.NEW
    assert r9.dedup_status == DedupStatus.IDEMPOTENCY_CONFLICT
    assert r9.contradiction_ids
