"""ORM models — physical schema, aligned to the assignment's Memory Event record.

* **raw_events** stores the assignment fields verbatim (``actor``, ``reliability``,
  ``related_entity_ids``, ``text``, ``entity_type``/``entity_id``). ``id`` IS the
  assignment ``event_id``; ``seq`` gives total replay order.
* **entities** are keyed by the assignment ``entity_id`` — memory is scoped
  directly by ``(entity_type, entity_id)``, no inference.
* **entity_relations** materializes ``related_entity_ids`` (account↔contact↔
  ticket↔policy) and powers policy isolation.
* **facts** carry the source event's ``reliability`` so resolution is reliability-first.
* **beliefs** is a self-invalidating, rebuildable snapshot; time-relative flags are
  computed at read.
* **context_builds** records each context build (cursor + belief hash) for diffing.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime


class RawEvent(Base):
    __tablename__ = "raw_events"
    __table_args__ = (
        Index("ix_raw_events_entity", "entity_type", "entity_id"),
        Index("ix_raw_events_source", "source"),
        {"sqlite_autoincrement": True},
    )

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String, unique=True, index=True)  # assignment event_id
    idempotency_key: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String, default="")
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String)
    related_entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    reliability: Mapped[str] = mapped_column(String, default="medium")
    text: Mapped[str] = mapped_column(String, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    payload_hash: Mapped[str] = mapped_column(String)
    fingerprint: Mapped[str] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime)
    dedup_status: Mapped[str] = mapped_column(String)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    idempotency_key: Mapped[str] = mapped_column(String, primary_key=True)
    first_event_id: Mapped[str | None] = mapped_column(ForeignKey("raw_events.id"), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    replay_count: Mapped[int] = mapped_column(Integer, default=0)
    last_replay_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # assignment entity_id
    entity_type: Mapped[str] = mapped_column(String)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_from_event_id: Mapped[str | None] = mapped_column(ForeignKey("raw_events.id"), nullable=True)


class EntityRelation(Base):
    """An edge from one entity to a related entity id (from related_entity_ids).

    ``to_entity_id`` is a plain string (not a FK) because a related entity may be
    referenced before it is itself ingested — forward references are allowed.
    """

    __tablename__ = "entity_relations"
    __table_args__ = (
        UniqueConstraint("from_entity_id", "to_entity_id", name="uq_entity_relation"),
        Index("ix_entity_relations_to", "to_entity_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    from_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    to_entity_id: Mapped[str] = mapped_column(String)
    via_event_id: Mapped[str] = mapped_column(ForeignKey("raw_events.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Fact(Base):
    __tablename__ = "facts"
    __table_args__ = (
        Index("ix_facts_entity_attribute", "entity_id", "attribute"),
        Index("ix_facts_attribute_value", "attribute", "value_hash"),
        UniqueConstraint("dedupe_key", name="uq_fact_dedupe_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    attribute: Mapped[str] = mapped_column(String)
    value: Mapped[dict] = mapped_column(JSON)
    value_hash: Mapped[str] = mapped_column(String)
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String)
    reliability: Mapped[str] = mapped_column(String, default="medium")
    polarity: Mapped[str] = mapped_column(String, default="assert")
    is_correction: Mapped[bool] = mapped_column(Boolean, default=False)
    extractor_name: Mapped[str] = mapped_column(String)
    extractor_version: Mapped[str] = mapped_column(String)
    source_event_id: Mapped[str] = mapped_column(ForeignKey("raw_events.id"))
    dedupe_key: Mapped[str] = mapped_column(String)


class FactEvidence(Base):
    __tablename__ = "fact_evidence"
    __table_args__ = (Index("ix_fact_evidence_fact", "fact_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    fact_id: Mapped[str] = mapped_column(ForeignKey("facts.id"), index=True)
    source_event_id: Mapped[str] = mapped_column(ForeignKey("raw_events.id"))
    relation: Mapped[str] = mapped_column(String, default="derived_from")
    locator: Mapped[dict] = mapped_column(JSON, default=dict)


class Belief(Base):
    __tablename__ = "beliefs"
    __table_args__ = (UniqueConstraint("entity_id", "attribute", name="uq_belief_entity_attribute"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    attribute: Mapped[str] = mapped_column(String)
    current_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    winning_fact_id: Mapped[str | None] = mapped_column(ForeignKey("facts.id"), nullable=True)
    winner_observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_contradicted: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    resolution_policy: Mapped[str] = mapped_column(String)
    resolution_trace: Mapped[list] = mapped_column(JSON, default=list)
    contributing_fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    through_seq: Mapped[int] = mapped_column(Integer, default=0)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    recompute_after: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Contradiction(Base):
    __tablename__ = "contradictions"
    __table_args__ = (
        Index("ix_contradictions_entity", "entity_id"),
        Index("ix_contradictions_status", "status"),
        UniqueConstraint("dedupe_key", name="uq_contradiction_dedupe_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"), nullable=True)
    attribute: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String)
    fact_id_a: Mapped[str | None] = mapped_column(ForeignKey("facts.id"), nullable=True)
    fact_id_b: Mapped[str | None] = mapped_column(ForeignKey("facts.id"), nullable=True)
    event_id_a: Mapped[str | None] = mapped_column(ForeignKey("raw_events.id"), nullable=True)
    event_id_b: Mapped[str | None] = mapped_column(ForeignKey("raw_events.id"), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="open")
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String)


class IdentityCandidate(Base):
    __tablename__ = "identity_candidates"
    __table_args__ = (
        Index("ix_identity_candidates_a", "entity_id_a"),
        Index("ix_identity_candidates_b", "entity_id_b"),
        UniqueConstraint("dedupe_key", name="uq_identity_candidate_dedupe_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_id_a: Mapped[str] = mapped_column(ForeignKey("entities.id"))
    entity_id_b: Mapped[str] = mapped_column(ForeignKey("entities.id"))
    reason: Mapped[str] = mapped_column(String)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="pending_review")
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime)
    dedupe_key: Mapped[str] = mapped_column(String)


class EventProcessing(Base):
    __tablename__ = "event_processing"
    __table_args__ = (Index("ix_event_processing_entity", "entity_id"),)

    event_id: Mapped[str] = mapped_column(ForeignKey("raw_events.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"), nullable=True)
    facts_created: Mapped[int] = mapped_column(Integer, default=0)
    extractor_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    decision: Mapped[dict] = mapped_column(JSON, default=dict)
    processed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    note: Mapped[str | None] = mapped_column(String, nullable=True)


class ReplayMetadata(Base):
    __tablename__ = "replay_metadata"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="running")
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str | None] = mapped_column(String, nullable=True)


class ContextBuild(Base):
    """A record of one context build for an entity — the cursor (``through_seq``)
    and a content hash of the belief set — so the next build can report what changed."""

    __tablename__ = "context_builds"
    __table_args__ = (Index("ix_context_builds_entity", "entity_id", "built_at"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    built_at: Mapped[datetime] = mapped_column(UTCDateTime)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime)
    through_seq: Mapped[int] = mapped_column(Integer, default=0)
    belief_hash: Mapped[str] = mapped_column(String)
    beliefs: Mapped[dict] = mapped_column(JSON, default=dict)
