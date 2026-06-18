"""Belief-resolution domain types.

The resolver is a pure function of ``(facts, as_of)`` — no wall-clock is read
inside it, which is what makes replay deterministic. A ``Resolution`` carries the
derived value, a fully reproducible trace, the verdict on every fact considered,
the contradictions detected, and two fields the projection cache needs:
``winner_observed_at`` and ``recompute_after`` (the earliest future instant at
which this resolution could change on its own — the next validity boundary or the
staleness flip). Nothing here touches the DB.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import ContradictionKind


class ResolutionStep(BaseModel):
    rule: str  # "scope" | "retraction" | "source_authority" | "recency" | "confidence" | "tiebreak" | ...
    detail: str
    winner_fact_id: str | None = None
    loser_fact_id: str | None = None


class CandidateVerdict(BaseModel):
    fact_id: str
    value: Any
    won: bool
    eliminated_by: str | None = None


class ContradictionFinding(BaseModel):
    kind: ContradictionKind
    entity_id: str
    attribute: str
    fact_id_a: str
    fact_id_b: str
    detail: dict[str, Any] = Field(default_factory=dict)


class Resolution(BaseModel):
    entity_id: str
    attribute: str
    as_of: datetime
    current_value: Any | None = None
    winning_fact_id: str | None = None
    winner_observed_at: datetime | None = None
    policy: str
    is_contradicted: bool = False
    is_stale: bool = False
    confidence: float = 0.0
    confidence_basis: str = ""
    # Earliest future instant at which this resolution could change with no new
    # event (next valid_from/valid_to boundary, or the staleness flip). Used to
    # self-invalidate the projection cache so it never rots.
    recompute_after: datetime | None = None
    considered_fact_ids: list[str] = Field(default_factory=list)
    contributing_fact_ids: list[str] = Field(default_factory=list)
    verdicts: list[CandidateVerdict] = Field(default_factory=list)
    trace: list[ResolutionStep] = Field(default_factory=list)
    findings: list[ContradictionFinding] = Field(default_factory=list)
