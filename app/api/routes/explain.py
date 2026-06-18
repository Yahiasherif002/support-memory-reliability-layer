"""Explain endpoint (Layer 7).

With ``?attribute=`` it explains a single belief; without it, every current
belief for the entity. ``response_model`` is left unset because the two shapes
differ — FastAPI still serializes the returned Pydantic model faithfully.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_explainability
from app.domain.explain import BeliefExplanation, EntityExplanation, EventExplanation
from app.services.explainability import ExplainabilityService

router = APIRouter(prefix="/v1", tags=["explain"])


@router.get("/events/{event_id}/explain", response_model=EventExplanation)
def explain_event(
    event_id: str,
    service: ExplainabilityService = Depends(get_explainability),
) -> EventExplanation:
    """Lineage for one raw event: idempotency classification, the identity
    decision, and what it produced."""
    explanation = service.explain_event(event_id)
    if explanation is None:
        raise HTTPException(status_code=404, detail=f"event {event_id!r} not found")
    return explanation


@router.get("/entities/{entity_id}/explain", response_model=None)
def explain(
    entity_id: str,
    attribute: str | None = None,
    as_of: datetime | None = None,
    service: ExplainabilityService = Depends(get_explainability),
) -> BeliefExplanation | EntityExplanation:
    if attribute is not None:
        explanation = service.explain_attribute(entity_id, attribute, as_of)
        if explanation is None:
            raise HTTPException(
                status_code=404,
                detail=f"no facts for attribute {attribute!r} on entity {entity_id!r}",
            )
        return explanation

    entity_explanation = service.explain_entity(entity_id, as_of)
    if entity_explanation is None:
        raise HTTPException(status_code=404, detail=f"entity {entity_id!r} not found")
    return entity_explanation
