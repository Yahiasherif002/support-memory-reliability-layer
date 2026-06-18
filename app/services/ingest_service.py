"""Layer 1 + ingestion pipeline (two durable phases), aligned to the Memory Event.

Phase 1 (own txn): atomic idempotency classification + durable raw event.
Phase 2 (own txn): scope to (entity_type, entity_id), record relations, extract
facts from text+payload, link evidence, project beliefs, detect identity ambiguity.
A retry returns the original logical result; processing failure preserves the raw
event for replay.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.clock import Clock, ensure_utc
from app.core.hashing import sha256_hex
from app.core.ids import deterministic_id
from app.core.logging import get_logger
from app.db.models import Contradiction, EventProcessing, Fact, FactEvidence, RawEvent
from app.db.repositories import (
    BeliefRepository,
    ContradictionRepository,
    EntityRepository,
    EventRepository,
    FactRepository,
    IdentityRepository,
)
from app.domain.enums import ContradictionKind, DedupStatus, ProcessingStatus
from app.domain.events import IngestResult, MemoryEvent
from app.policies.reliability import weight as reliability_weight
from app.services.belief_resolver import ProjectionService
from app.services.extraction import ExtractorRegistry, default_registry
from app.services.identity_service import IdentityService
from app.services.snapshot_manager import SnapshotManager

logger = get_logger(__name__)


@dataclass
class _Phase1:
    dedup: DedupStatus
    event_id: str
    seq: int
    result: IngestResult | None = None


def event_fingerprint(event: MemoryEvent) -> str:
    return sha256_hex({
        "source": str(event.source), "entity_type": str(event.entity_type), "entity_id": event.entity_id,
        "related_entity_ids": sorted(event.related_entity_ids), "reliability": str(event.reliability),
        "actor": event.actor, "text": event.text, "payload": event.payload,
        "occurred_at": ensure_utc(event.occurred_at).isoformat(),
    })


class IngestService:
    def __init__(self, session: Session, clock: Clock, registry: ExtractorRegistry | None = None) -> None:
        self.session = session
        self.clock = clock
        self.events = EventRepository(session)
        self.entities = EntityRepository(session)
        self.facts = FactRepository(session)
        self.contradictions = ContradictionRepository(session)
        self.identities = IdentityRepository(session)
        self.registry = registry or default_registry()
        self.identity = IdentityService(self.entities, self.identities, self.facts)
        self.projection = ProjectionService(
            facts=self.facts, snapshots=SnapshotManager(BeliefRepository(session)),
            contradictions=self.contradictions, entities=self.entities, clock=clock)

    def ingest(self, event: MemoryEvent) -> IngestResult:
        phase1 = self._record(event)
        if phase1.dedup is not DedupStatus.NEW:
            return phase1.result
        try:
            return self._process(phase1.event_id, phase1.seq)
        except Exception:
            self.session.rollback()
            logger.exception("processing failed for %s; raw event preserved", phase1.event_id)
            self._mark_error(phase1.event_id)
            return IngestResult(event_id=phase1.event_id, seq=phase1.seq, dedup_status=DedupStatus.NEW,
                                processed=False, message="Stored durably; processing failed and is available for replay.")

    # --- phase 1 --------------------------------------------------------
    def _record(self, event: MemoryEvent) -> _Phase1:
        now = self.clock.now()
        occurred = ensure_utc(event.occurred_at)
        fingerprint = event_fingerprint(event)
        payload_hash = sha256_hex(event.payload)
        record, inserted = self.events.try_register_idempotency(event.idempotency_key, fingerprint, now)

        if inserted:
            raw = self.events.add(self._raw(event, occurred, now, fingerprint, payload_hash, DedupStatus.NEW))
            record.first_event_id = raw.id
            self.session.commit()
            return _Phase1(DedupStatus.NEW, raw.id, raw.seq)

        if record.fingerprint == fingerprint:
            self.events.bump_replay(record, now)
            self.session.commit()
            if record.result is not None:  # idempotent response: return the original result
                cached = IngestResult.model_validate(record.result)
                cached.dedup_status = DedupStatus.DUPLICATE_REPLAY
                cached.canonical_event_id = record.first_event_id
                cached.message = "Idempotent replay: original result returned; nothing re-created."
                return _Phase1(DedupStatus.DUPLICATE_REPLAY, cached.event_id, cached.seq, cached)
            canonical = self.events.get(record.first_event_id) if record.first_event_id else None
            if canonical is not None:  # first delivery never finished → complete it now
                return _Phase1(DedupStatus.NEW, canonical.id, canonical.seq)
            return _Phase1(DedupStatus.DUPLICATE_REPLAY, record.first_event_id or "", 0,
                           IngestResult(event_id=record.first_event_id or "", seq=0,
                                        dedup_status=DedupStatus.DUPLICATE_REPLAY, processed=False,
                                        canonical_event_id=record.first_event_id, message="Duplicate delivery."))

        # same key, different fingerprint → conflict (kept as evidence)
        raw = self.events.add(self._raw(event, occurred, now, fingerprint, payload_hash, DedupStatus.IDEMPOTENCY_CONFLICT))
        con_id = self._record_idempotency_conflict(record, raw, fingerprint, now)
        self.events.upsert_processing(EventProcessing(
            event_id=raw.id, status=str(ProcessingStatus.CONFLICT), facts_created=0, extractor_versions={},
            decision={"idempotency": "conflict", "first_event_id": record.first_event_id},
            processed_at=now, note=f"idempotency conflict with {record.first_event_id}"))
        self.session.commit()
        return _Phase1(DedupStatus.IDEMPOTENCY_CONFLICT, raw.id, raw.seq,
                       IngestResult(event_id=raw.id, seq=raw.seq, dedup_status=DedupStatus.IDEMPOTENCY_CONFLICT,
                                    processed=False, contradiction_ids=[con_id], canonical_event_id=record.first_event_id,
                                    message="Idempotency key reused with a different payload; stored and flagged, not processed."))

    def _raw(self, event, occurred, now, fingerprint, payload_hash, dedup) -> RawEvent:
        return RawEvent(
            id=event.event_id, idempotency_key=event.idempotency_key, source=str(event.source),
            actor=event.actor, entity_type=str(event.entity_type), entity_id=event.entity_id,
            related_entity_ids=list(event.related_entity_ids), reliability=str(event.reliability),
            text=event.text, payload=event.payload, payload_hash=payload_hash, fingerprint=fingerprint,
            occurred_at=occurred, received_at=now, dedup_status=str(dedup))

    # --- phase 2 --------------------------------------------------------
    def _process(self, event_id: str, seq: int) -> IngestResult:
        raw = self.events.get(event_id)
        scope = self.identity.scope(raw)
        entity = scope.entity

        extractor = self.registry.get(raw.source)
        facts_created = 0
        affected: set[str] = set()
        versions: dict[str, str] = {}
        if extractor is not None:
            versions = {extractor.name: extractor.version}
            for extracted in extractor.extract(raw):
                if self._materialize_fact(entity.id, raw, extracted, extractor.name, extractor.version):
                    facts_created += 1
                affected.add(extracted.attribute)

        contradiction_ids: list[str] = []
        for attribute in sorted(affected):
            _b, cids = self.projection.project_attribute(entity.id, attribute)
            contradiction_ids.extend(cids)

        candidate_ids = self.identity.detect_ambiguity(raw.received_at)

        self.events.upsert_processing(EventProcessing(
            event_id=raw.id, status=str(ProcessingStatus.EXTRACTED), entity_id=entity.id,
            facts_created=facts_created, extractor_versions=versions, decision=scope.decision,
            processed_at=raw.received_at, note=None if extractor is not None else "no extractor for source"))

        result = IngestResult(event_id=raw.id, seq=seq, dedup_status=DedupStatus.NEW, processed=True,
                              entity_id=entity.id, facts_created=facts_created, contradiction_ids=contradiction_ids,
                              identity_candidate_ids=candidate_ids, message="Ingested.")
        self._cache_result(raw, result)
        self.session.commit()
        return result

    def _materialize_fact(self, entity_id, raw, extracted, extractor_name, extractor_version) -> bool:
        valid_from = ensure_utc(extracted.valid_from) if extracted.valid_from else raw.occurred_at
        valid_to = ensure_utc(extracted.valid_to) if extracted.valid_to else None
        value_hash = sha256_hex(extracted.value)
        confidence = extracted.confidence if extracted.confidence is not None else reliability_weight(raw.reliability)
        dedupe_key = sha256_hex([entity_id, extracted.attribute, value_hash, valid_from.isoformat(),
                                 raw.id, str(extracted.polarity), extractor_name, extractor_version])
        fact = Fact(
            id=deterministic_id("fact", dedupe_key), entity_id=entity_id, attribute=extracted.attribute,
            value=extracted.value, value_hash=value_hash, valid_from=valid_from, valid_to=valid_to,
            observed_at=raw.occurred_at, recorded_at=raw.received_at, confidence=confidence, source=raw.source,
            reliability=raw.reliability, polarity=str(extracted.polarity), is_correction=extracted.is_correction,
            extractor_name=extractor_name, extractor_version=extractor_version, source_event_id=raw.id, dedupe_key=dedupe_key)
        stored, created = self.facts.add_idempotent(fact)
        if created:
            self.facts.add_evidence(FactEvidence(
                id=deterministic_id("ev", stored.id, raw.id), fact_id=stored.id, source_event_id=raw.id,
                relation="derived_from", locator=extracted.locator))
        return created

    def _record_idempotency_conflict(self, record, raw, fingerprint, now) -> str:
        dedupe_key = sha256_hex(["idempotency_conflict", record.idempotency_key, record.fingerprint, fingerprint])
        row, _ = self.contradictions.add_idempotent(Contradiction(
            id=deterministic_id("con", dedupe_key), entity_id=None, attribute=None,
            kind=str(ContradictionKind.IDEMPOTENCY_CONFLICT), event_id_a=record.first_event_id, event_id_b=raw.id,
            detail={"idempotency_key": record.idempotency_key, "first_fingerprint": record.fingerprint,
                    "conflicting_fingerprint": fingerprint},
            status="open", detected_at=now, updated_at=now, dedupe_key=dedupe_key))
        return row.id

    def _cache_result(self, raw: RawEvent, result: IngestResult) -> None:
        record = self.events.get_idempotency(raw.idempotency_key)
        if record is not None:
            record.result = result.model_dump(mode="json")

    def _mark_error(self, event_id: str) -> None:
        try:
            self.events.upsert_processing(EventProcessing(
                event_id=event_id, status=str(ProcessingStatus.ERROR), facts_created=0, extractor_versions={},
                decision={"error": True}, processed_at=self.clock.now(), note=traceback.format_exc(limit=3)))
            self.session.commit()
        except Exception:  # pragma: no cover
            self.session.rollback()
