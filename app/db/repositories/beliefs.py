"""Belief snapshot store (self-invalidating read-model cache)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Belief


class BeliefRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, entity_id: str, attribute: str) -> Belief | None:
        return self.session.execute(
            select(Belief).where(
                Belief.entity_id == entity_id, Belief.attribute == attribute
            )
        ).scalar_one_or_none()

    def list_for_entity(self, entity_id: str) -> list[Belief]:
        return list(
            self.session.execute(
                select(Belief)
                .where(Belief.entity_id == entity_id)
                .order_by(Belief.attribute)
            )
            .scalars()
            .all()
        )

    def upsert(self, belief: Belief) -> Belief:
        existing = self.get(belief.entity_id, belief.attribute)
        if existing is None:
            self.session.add(belief)
            self.session.flush()
            return belief
        existing.current_value = belief.current_value
        existing.winning_fact_id = belief.winning_fact_id
        existing.winner_observed_at = belief.winner_observed_at
        existing.is_contradicted = belief.is_contradicted
        existing.confidence = belief.confidence
        existing.resolution_policy = belief.resolution_policy
        existing.resolution_trace = belief.resolution_trace
        existing.contributing_fact_ids = belief.contributing_fact_ids
        existing.through_seq = belief.through_seq
        existing.as_of = belief.as_of
        existing.computed_at = belief.computed_at
        existing.recompute_after = belief.recompute_after
        self.session.flush()
        return existing

    def delete_all(self) -> int:
        result = self.session.execute(delete(Belief))
        return result.rowcount or 0
