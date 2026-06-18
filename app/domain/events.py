"""The assignment's Memory Event record and the ingest result.

``MemoryEvent`` mirrors the brief's schema field-for-field, so the provided
dataset is accepted with **no modification**. There is no ``event_type``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import DedupStatus, EntityType, Reliability, Source


class MemoryEvent(BaseModel):
    event_id: str
    idempotency_key: str
    occurred_at: datetime
    source: Source
    actor: str = ""
    entity_type: EntityType
    entity_id: str
    related_entity_ids: list[str] = Field(default_factory=list)
    reliability: Reliability = Reliability.MEDIUM
    text: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class IngestResult(BaseModel):
    event_id: str
    seq: int
    dedup_status: DedupStatus
    processed: bool
    entity_id: str | None = None
    facts_created: int = 0
    contradiction_ids: list[str] = Field(default_factory=list)
    identity_candidate_ids: list[str] = Field(default_factory=list)
    canonical_event_id: str | None = None
    message: str = ""
