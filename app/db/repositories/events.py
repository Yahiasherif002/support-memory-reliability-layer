"""Raw event store + atomic idempotency registry + processing log + replay checkpoints."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db.models import EventProcessing, IdempotencyKey, RawEvent, ReplayMetadata


class EventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event: RawEvent) -> RawEvent:
        self.session.add(event)
        self.session.flush()
        return event

    def get(self, event_id: str) -> RawEvent | None:
        return self.session.execute(select(RawEvent).where(RawEvent.id == event_id)).scalar_one_or_none()

    def list_ordered(self) -> list[RawEvent]:
        return list(self.session.execute(select(RawEvent).order_by(RawEvent.seq)).scalars().all())

    def list_new_after(self, after_seq: int) -> list[RawEvent]:
        return list(
            self.session.execute(
                select(RawEvent).where(RawEvent.dedup_status == "new", RawEvent.seq > after_seq).order_by(RawEvent.seq)
            ).scalars().all()
        )

    def max_seq(self) -> int:
        return self.session.execute(select(func.max(RawEvent.seq))).scalar() or 0

    def entity_max_seq(self, entity_id: str) -> int:
        return self.session.execute(
            select(func.max(RawEvent.seq)).where(RawEvent.entity_id == entity_id)
        ).scalar() or 0

    def entity_events_after(self, entity_id: str, seq: int) -> list[RawEvent]:
        return list(self.session.execute(
            select(RawEvent).where(RawEvent.entity_id == entity_id, RawEvent.seq > seq).order_by(RawEvent.seq)
        ).scalars().all())

    # --- idempotency (atomic upsert, keyed globally by idempotency_key) ---
    def get_idempotency(self, key: str) -> IdempotencyKey | None:
        return self.session.get(IdempotencyKey, key)

    def try_register_idempotency(self, key: str, fingerprint: str, now: datetime) -> tuple[IdempotencyKey, bool]:
        stmt = (
            sqlite_insert(IdempotencyKey)
            .values(idempotency_key=key, first_event_id=None, fingerprint=fingerprint, created_at=now, replay_count=0)
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
        )
        inserted = (self.session.execute(stmt).rowcount or 0) == 1
        return self.session.get(IdempotencyKey, key), inserted

    def bump_replay(self, record: IdempotencyKey, now: datetime) -> None:
        record.replay_count = (record.replay_count or 0) + 1
        record.last_replay_at = now
        self.session.flush()

    # --- processing log + replay checkpoints ----------------------------
    def upsert_processing(self, processing: EventProcessing) -> EventProcessing:
        merged = self.session.merge(processing)
        self.session.flush()
        return merged

    def get_processing(self, event_id: str) -> EventProcessing | None:
        return self.session.get(EventProcessing, event_id)

    def start_replay(self, run: ReplayMetadata) -> ReplayMetadata:
        self.session.add(run)
        self.session.flush()
        return run

    def latest_incomplete_replay(self, kind: str) -> ReplayMetadata | None:
        return self.session.execute(
            select(ReplayMetadata).where(ReplayMetadata.kind == kind, ReplayMetadata.status == "running")
            .order_by(ReplayMetadata.started_at.desc()).limit(1)
        ).scalar_one_or_none()
