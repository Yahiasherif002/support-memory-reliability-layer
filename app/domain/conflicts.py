"""Unified conflict views (contradictions + identity candidates) and the
status-update body for the PATCH endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConflictItem(BaseModel):
    """A single row in the unified ``/conflicts`` feed.

    ``type`` discriminates the two underlying sources so a UI can route them,
    while a common shape lets a rep scan everything in one list.
    """

    id: str
    type: Literal["contradiction", "identity_candidate"]
    kind: str  # contradiction kind, or "identity_ambiguity"
    status: str
    entity_id: str | None = None
    attribute: str | None = None
    detected_at: datetime
    detail: dict[str, Any] = Field(default_factory=dict)
    refs: dict[str, Any] = Field(default_factory=dict)  # fact/event/entity ids


class ConflictStatusUpdate(BaseModel):
    """PATCH body. Resolution is a *workflow* transition — never destructive."""

    status: str
    note: str | None = None
