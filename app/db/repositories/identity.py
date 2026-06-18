"""Identity-candidate records (possible-same-entity, never auto-merged)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IdentityCandidate


class IdentityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_idempotent(
        self, candidate: IdentityCandidate
    ) -> tuple[IdentityCandidate, bool]:
        existing = self.session.execute(
            select(IdentityCandidate).where(
                IdentityCandidate.dedupe_key == candidate.dedupe_key
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False
        self.session.add(candidate)
        self.session.flush()
        return candidate, True

    def get(self, candidate_id: str) -> IdentityCandidate | None:
        return self.session.get(IdentityCandidate, candidate_id)

    def list(
        self, *, entity_id: str | None = None, status: str | None = None
    ) -> list[IdentityCandidate]:
        stmt = select(IdentityCandidate)
        if entity_id is not None:
            stmt = stmt.where(
                (IdentityCandidate.entity_id_a == entity_id)
                | (IdentityCandidate.entity_id_b == entity_id)
            )
        if status is not None:
            stmt = stmt.where(IdentityCandidate.status == status)
        stmt = stmt.order_by(IdentityCandidate.detected_at.desc())
        return list(self.session.execute(stmt).scalars().all())

    def set_status(self, candidate_id: str, status: str) -> IdentityCandidate | None:
        row = self.get(candidate_id)
        if row is None:
            return None
        row.status = status
        self.session.flush()
        return row
