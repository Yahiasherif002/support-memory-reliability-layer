"""Snapshot Manager — owns the belief read-model projection.

The belief snapshot is a *rebuildable cache*. It stores only event-deterministic
data plus ``recompute_after`` (the earliest future instant the resolution could
change on its own). A direct consumer of the table must treat a row as valid only
while ``through_seq`` is current and ``now < recompute_after``; the read endpoints
don't depend on it (they recompute through the resolver), so context and explain
can never serve a rotted snapshot.
"""

from __future__ import annotations

from datetime import datetime

from app.core.ids import deterministic_id
from app.db.models import Belief
from app.db.repositories import BeliefRepository
from app.domain.beliefs import Resolution


class SnapshotManager:
    def __init__(self, beliefs: BeliefRepository) -> None:
        self.beliefs = beliefs

    def get(self, entity_id: str, attribute: str) -> Belief | None:
        return self.beliefs.get(entity_id, attribute)

    @staticmethod
    def is_time_valid(snapshot: Belief, now: datetime) -> bool:
        return snapshot.recompute_after is None or now < snapshot.recompute_after

    def write(self, res: Resolution, *, through_seq: int, computed_at: datetime) -> Belief:
        return self.beliefs.upsert(
            Belief(
                id=deterministic_id("blf", res.entity_id, res.attribute),
                entity_id=res.entity_id,
                attribute=res.attribute,
                current_value={"value": res.current_value},
                winning_fact_id=res.winning_fact_id,
                winner_observed_at=res.winner_observed_at,
                is_contradicted=res.is_contradicted,
                confidence=res.confidence,
                resolution_policy=res.policy,
                resolution_trace=[step.model_dump() for step in res.trace],
                contributing_fact_ids=res.contributing_fact_ids,
                through_seq=through_seq,
                as_of=res.as_of,
                computed_at=computed_at,
                recompute_after=res.recompute_after,
            )
        )

    def delete_all(self) -> int:
        return self.beliefs.delete_all()
