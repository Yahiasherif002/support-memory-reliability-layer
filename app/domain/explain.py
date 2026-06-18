"""Explainability DTOs (Layer 7 output).

An explanation answers "why do we believe X?" end to end: the derived value, the
ordered resolution trace, the winning fact, **every** competing fact (with the
rule that eliminated it), and each fact's evidence back to the raw events and the
exact payload field it was read from. Everything is reconstructable from stored
data — no hidden state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.beliefs import ResolutionStep


class EvidenceItem(BaseModel):
    event_id: str
    source: str
    reliability: str | None = None
    actor: str | None = None
    occurred_at: datetime
    relation: str
    locator: dict[str, Any] = Field(default_factory=dict)
    payload_excerpt: Any = None  # the located value, or the whole payload if unlocated
    text: str | None = None


class FactExplanation(BaseModel):
    fact_id: str
    attribute: str
    value: Any
    source: str
    reliability: str | None = None
    confidence: float
    polarity: str
    valid_from: datetime
    valid_to: datetime | None = None
    observed_at: datetime
    recorded_at: datetime
    is_winner: bool = False
    eliminated_by: str | None = None
    extractor: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class BeliefExplanation(BaseModel):
    entity_id: str
    attribute: str
    as_of: datetime
    current_value: Any | None = None
    confidence: float = 0.0
    confidence_basis: str = ""
    is_stale: bool = False
    is_contradicted: bool = False
    policy: str = ""
    winning_fact_id: str | None = None
    resolution_trace: list[ResolutionStep] = Field(default_factory=list)
    facts: list[FactExplanation] = Field(default_factory=list)


class EventExplanation(BaseModel):
    """Event-level lineage: how one raw event was classified (idempotency), which
    entity it resolved to and why (identity), and what it produced (facts).
    Explainability beyond belief resolution."""

    event_id: str
    source: str
    entity_type: str
    actor: str = ""
    reliability: str | None = None
    occurred_at: datetime
    received_at: datetime
    dedup_status: str
    processing_status: str | None = None
    entity_id: str | None = None
    facts_created: int = 0
    extractor_versions: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class EntityExplanation(BaseModel):
    """All current beliefs for an entity, each fully explained."""

    entity_id: str
    as_of: datetime
    beliefs: list[BeliefExplanation] = Field(default_factory=list)
