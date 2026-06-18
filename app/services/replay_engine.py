"""Replay Engine — rebuild ALL derived state from the immutable raw log.

Derived rows are content-addressed and timestamped from their raw event, so
replaying ``raw_events`` in ``seq`` order reproduces byte-identical state. Only
``raw_events`` / ``idempotency_keys`` (and idempotency-conflict artifacts) are
authoritative. Checkpointed via ``replay_metadata`` → resumable.
"""

from __future__ import annotations

from sqlalchemy import delete

from app.core.clock import Clock
from app.core.ids import new_id
from app.db.models import (
    Belief, ContextBuild, Contradiction, Entity, EntityRelation, EventProcessing,
    Fact, FactEvidence, IdentityCandidate, ReplayMetadata,
)
from app.db.repositories import EventRepository
from app.services.extraction import ExtractorRegistry
from app.services.ingest_service import IngestService


class ReplayEngine:
    def __init__(self, session, clock: Clock, registry: ExtractorRegistry | None = None) -> None:
        self.session = session
        self.clock = clock
        self.events = EventRepository(session)
        self.ingest = IngestService(session, clock, registry)

    def rebuild_all(self, *, batch_size: int = 500, resume: bool = False) -> dict:
        run = self.events.latest_incomplete_replay("rebuild_all") if resume else None
        if run is None:
            self._truncate_derived()
            now = self.clock.now()
            run = self.events.start_replay(ReplayMetadata(
                id=new_id("rpl"), kind="rebuild_all", last_seq=0, status="running",
                started_at=now, updated_at=now, stats={}))
            self.session.commit()
        return self._run(run, batch_size)

    def _run(self, run: ReplayMetadata, batch_size: int) -> dict:
        processed = 0
        while True:
            batch = self.events.list_new_after(run.last_seq)[:batch_size]
            if not batch:
                break
            for event in batch:
                self.ingest._process(event.id, event.seq)
                run.last_seq = event.seq
                processed += 1
            run.updated_at = self.clock.now()
            self.session.commit()
        run.status = "completed"
        run.updated_at = self.clock.now()
        run.stats = {"events_processed": processed}
        self.session.commit()
        return {"events_processed": processed, "run_id": run.id, "through_seq": run.last_seq}

    def _truncate_derived(self) -> None:
        self.session.execute(delete(ContextBuild))
        self.session.execute(delete(FactEvidence))
        self.session.execute(delete(Belief))
        self.session.execute(delete(Contradiction).where(Contradiction.kind == "belief_value_conflict"))
        self.session.execute(delete(EventProcessing).where(EventProcessing.status.in_(["extracted", "error"])))
        self.session.execute(delete(IdentityCandidate))
        self.session.execute(delete(Fact))
        self.session.execute(delete(EntityRelation))
        self.session.execute(delete(Entity))
        self.session.commit()
