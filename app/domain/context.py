"""Context pack DTOs (Layer 6).

Compact, evidence-linked snapshot for a rep. ``applicable_policies`` are pulled
**only** from policy entities related to this account (policy isolation), so one
account's policy can never leak into another's context.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.conflicts import ConflictItem
from app.domain.entities import EntityView


class ProvenanceRef(BaseModel):
    fact_id: str | None = None
    event_ids: list[str] = Field(default_factory=list)
    reliability: str | None = None
    explain: str | None = None


class ContextBelief(BaseModel):
    attribute: str
    value: Any
    confidence: float
    reliability: str | None = None
    is_stale: bool = False
    is_contradicted: bool = False
    salience: float = 0.0
    provenance: ProvenanceRef


class ContextPolicy(BaseModel):
    policy_entity_id: str
    name: str
    rule: Any
    reliability: str | None = None
    provenance: ProvenanceRef


class ContextActivity(BaseModel):
    fact_id: str
    attribute: str
    value: Any
    source: str
    reliability: str
    observed_at: datetime
    event_id: str


class IdentityWarning(BaseModel):
    candidate_id: str
    other_entity_id: str
    reason: str
    score: float
    status: str


class ContextPack(BaseModel):
    entity: EntityView
    generated_at: datetime
    as_of: datetime
    budget: int
    beliefs: list[ContextBelief] = Field(default_factory=list)
    applicable_policies: list[ContextPolicy] = Field(default_factory=list)
    open_contradictions: list[ConflictItem] = Field(default_factory=list)
    identity_warnings: list[IdentityWarning] = Field(default_factory=list)
    recent_activity: list[ContextActivity] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
