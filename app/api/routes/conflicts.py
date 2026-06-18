"""Conflicts endpoint — the unified contradiction + identity-ambiguity feed."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_clock, get_conflict_service, get_session
from app.core.clock import Clock
from app.domain.conflicts import ConflictItem, ConflictStatusUpdate
from app.services.conflict_service import ConflictService

router = APIRouter(prefix="/v1", tags=["conflicts"])


@router.get("/conflicts", response_model=list[ConflictItem])
def list_conflicts(
    entity_id: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    service: ConflictService = Depends(get_conflict_service),
) -> list[ConflictItem]:
    return service.list_conflicts(entity_id=entity_id, kind=kind, status=status)


@router.patch("/conflicts/{conflict_id}", response_model=ConflictItem)
def update_conflict(
    conflict_id: str,
    body: ConflictStatusUpdate,
    service: ConflictService = Depends(get_conflict_service),
    session: Session = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> ConflictItem:
    # A status transition is a workflow action, never destructive: the underlying
    # facts/events that triggered the conflict are untouched.
    item = service.update_status(conflict_id, body.status, body.note, clock.now())
    if item is None:
        raise HTTPException(status_code=404, detail=f"conflict {conflict_id!r} not found")
    session.commit()
    return item
