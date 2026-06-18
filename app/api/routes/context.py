"""Context endpoint (Layer 6) + the 'what changed since last build' diff."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_context_builder, get_context_diff
from app.domain.context import ContextPack
from app.services.context_builder import ContextBuilder
from app.services.context_diff import ContextDiffService

router = APIRouter(prefix="/v1", tags=["context"])


@router.get("/entities/{entity_id}/context", response_model=ContextPack)
def get_context(
    entity_id: str,
    budget: int | None = Query(default=None, ge=1, le=100),
    as_of: datetime | None = None,
    builder: ContextBuilder = Depends(get_context_builder),
) -> ContextPack:
    pack = builder.build(entity_id, budget=budget, as_of=as_of)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"entity {entity_id!r} not found")
    return pack


@router.get("/entities/{entity_id}/context/diff")
def get_context_diff(
    entity_id: str,
    as_of: datetime | None = None,
    persist: bool = True,
    differ: ContextDiffService = Depends(get_context_diff),
) -> dict:
    out = differ.build_and_diff(entity_id, as_of=as_of, persist=persist)
    if out is None:
        raise HTTPException(status_code=404, detail=f"entity {entity_id!r} not found")
    return out
