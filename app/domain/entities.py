"""Entity read view."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EntityView(BaseModel):
    id: str
    entity_type: str
    display_name: str | None = None
    created_at: datetime
    related_entity_ids: list[str] = Field(default_factory=list)
