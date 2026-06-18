"""Unified conflict feed.

Contradictions and identity candidates live in separate tables (they have
different shapes and lifecycles) but a support rep wants one place to see "what
is uncertain about this customer". This service maps both into the common
``ConflictItem`` shape and owns the non-destructive status transitions.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Contradiction, IdentityCandidate
from app.db.repositories import ContradictionRepository, IdentityRepository
from app.domain.conflicts import ConflictItem

IDENTITY_KIND = "identity_ambiguity"


def contradiction_to_item(c: Contradiction) -> ConflictItem:
    return ConflictItem(
        id=c.id,
        type="contradiction",
        kind=c.kind,
        status=c.status,
        entity_id=c.entity_id,
        attribute=c.attribute,
        detected_at=c.detected_at,
        detail=c.detail or {},
        refs={
            "fact_id_a": c.fact_id_a,
            "fact_id_b": c.fact_id_b,
            "event_id_a": c.event_id_a,
            "event_id_b": c.event_id_b,
            "resolution_note": c.resolution_note,
        },
    )


def identity_to_item(ic: IdentityCandidate) -> ConflictItem:
    return ConflictItem(
        id=ic.id,
        type="identity_candidate",
        kind=IDENTITY_KIND,
        status=ic.status,
        entity_id=ic.entity_id_a,
        attribute=None,
        detected_at=ic.detected_at,
        detail={"reason": ic.reason, "score": ic.score, **(ic.evidence or {})},
        refs={"entity_id_a": ic.entity_id_a, "entity_id_b": ic.entity_id_b},
    )


class ConflictService:
    def __init__(self, session: Session) -> None:
        self.contradictions = ContradictionRepository(session)
        self.identities = IdentityRepository(session)

    def list_conflicts(
        self,
        *,
        entity_id: str | None = None,
        kind: str | None = None,
        status: str | None = None,
    ) -> list[ConflictItem]:
        items: list[ConflictItem] = []
        # Contradictions only when the kind filter isn't asking purely for identity.
        if kind != IDENTITY_KIND:
            items.extend(
                contradiction_to_item(c)
                for c in self.contradictions.list(entity_id=entity_id, kind=kind, status=status)
            )
        # Identity candidates only when not filtering to a contradiction kind.
        if kind in (None, IDENTITY_KIND):
            items.extend(
                identity_to_item(ic)
                for ic in self.identities.list(entity_id=entity_id, status=status)
            )
        items.sort(key=lambda i: i.detected_at, reverse=True)
        return items

    def update_status(
        self, conflict_id: str, status: str, note: str | None, now=None
    ) -> ConflictItem | None:
        contradiction = self.contradictions.set_status(conflict_id, status, note, now)
        if contradiction is not None:
            return contradiction_to_item(contradiction)
        candidate = self.identities.set_status(conflict_id, status)
        if candidate is not None:
            return identity_to_item(candidate)
        return None
