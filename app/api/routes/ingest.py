"""Ingest endpoint — accepts the assignment Memory Event record directly.

Always 200; the body's ``dedup_status`` classifies the delivery (new /
duplicate_replay / idempotency_conflict). A retry returns the original result.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_ingest_service
from app.domain.events import IngestResult, MemoryEvent
from app.services.ingest_service import IngestService

router = APIRouter(prefix="/v1", tags=["ingest"])


@router.post("/events:ingest", response_model=IngestResult)
def ingest_event(event: MemoryEvent, service: IngestService = Depends(get_ingest_service)) -> IngestResult:
    return service.ingest(event)


@router.post("/events:ingest-batch", response_model=list[IngestResult])
def ingest_batch(events: list[MemoryEvent], service: IngestService = Depends(get_ingest_service)) -> list[IngestResult]:
    return [service.ingest(event) for event in events]
