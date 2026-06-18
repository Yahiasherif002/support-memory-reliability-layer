"""Contradiction records with lifecycle (open → acknowledged/resolved/auto_closed)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Contradiction


class ContradictionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_idempotent(self, contradiction: Contradiction) -> tuple[Contradiction, bool]:
        existing = self.session.execute(
            select(Contradiction).where(
                Contradiction.dedupe_key == contradiction.dedupe_key
            )
        ).scalar_one_or_none()
        if existing is not None:
            # If a previously auto-closed conflict recurs, reopen it.
            if existing.status == "auto_closed":
                existing.status = "open"
                existing.updated_at = contradiction.detected_at
                self.session.flush()
            return existing, False
        self.session.add(contradiction)
        self.session.flush()
        return contradiction, True

    def get(self, contradiction_id: str) -> Contradiction | None:
        return self.session.get(Contradiction, contradiction_id)

    def list(
        self,
        *,
        entity_id: str | None = None,
        attribute: str | None = None,
        kind: str | None = None,
        status: str | None = None,
    ) -> list[Contradiction]:
        stmt = select(Contradiction)
        if entity_id is not None:
            stmt = stmt.where(Contradiction.entity_id == entity_id)
        if attribute is not None:
            stmt = stmt.where(Contradiction.attribute == attribute)
        if kind is not None:
            stmt = stmt.where(Contradiction.kind == kind)
        if status is not None:
            stmt = stmt.where(Contradiction.status == status)
        return list(
            self.session.execute(stmt.order_by(Contradiction.detected_at.desc()))
            .scalars()
            .all()
        )

    def list_live_for_attribute(self, entity_id: str, attribute: str) -> list[Contradiction]:
        """Open belief-value conflicts for one (entity, attribute) — used by the
        projector to auto-close conflicts that are no longer jointly valid."""
        return list(
            self.session.execute(
                select(Contradiction).where(
                    Contradiction.entity_id == entity_id,
                    Contradiction.attribute == attribute,
                    Contradiction.kind == "belief_value_conflict",
                    Contradiction.status == "open",
                )
            )
            .scalars()
            .all()
        )

    def auto_close(self, contradiction: Contradiction, now: datetime, note: str) -> None:
        contradiction.status = "auto_closed"
        contradiction.updated_at = now
        contradiction.resolution_note = note
        self.session.flush()

    def set_status(
        self, contradiction_id: str, status: str, note: str | None, now: datetime | None = None
    ) -> Contradiction | None:
        row = self.get(contradiction_id)
        if row is None:
            return None
        row.status = status
        row.updated_at = now
        if note is not None:
            row.resolution_note = note
        self.session.flush()
        return row

    def delete_belief_conflicts(self) -> int:
        """Used by a full rebuild: value conflicts are re-derived from facts;
        idempotency conflicts are ingest artifacts and are preserved."""
        result = self.session.execute(
            delete(Contradiction).where(Contradiction.kind == "belief_value_conflict")
        )
        return result.rowcount or 0
