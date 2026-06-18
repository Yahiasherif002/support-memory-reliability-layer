"""Mid-test scope change — "What changed since the last context build?"

Each build records a cursor (``through_seq`` for the entity) and a content hash of
the belief set. The next build diffs the current belief set against the stored one
(added / removed / changed beliefs) and lists the raw events that arrived since the
last cursor. Beliefs are reconstructed through the shared engine, so the diff is
consistent with /context and /explain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import Clock, ensure_utc
from app.core.hashing import sha256_hex
from app.core.ids import new_id
from app.db.models import ContextBuild
from app.db.repositories import ContextBuildRepository, EntityRepository, EventRepository, FactRepository
from app.services.belief_resolver import BeliefResolutionEngine


class ContextDiffService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self.clock = clock
        self.entities = EntityRepository(session)
        self.events = EventRepository(session)
        self.builds = ContextBuildRepository(session)
        self.engine = BeliefResolutionEngine(FactRepository(session), clock)
        self.session = session

    def _belief_set(self, entity_id: str, as_of: datetime) -> dict[str, Any]:
        return {
            attr: {"value": r.current_value, "winning_fact_id": r.winning_fact_id,
                   "confidence": r.confidence, "is_contradicted": r.is_contradicted, "is_stale": r.is_stale}
            for attr, r in self.engine.reconstruct_entity(entity_id, as_of).items()
            if r.current_value is not None
        }

    def build_and_diff(self, entity_id: str, *, as_of: datetime | None = None, persist: bool = True) -> dict | None:
        if self.entities.get(entity_id) is None:
            return None
        now = self.clock.now()
        as_of = ensure_utc(as_of) if as_of else now

        previous = self.builds.latest(entity_id)
        current = self._belief_set(entity_id, as_of)
        belief_hash = sha256_hex(current)
        through_seq = self.events.entity_max_seq(entity_id)

        prev_beliefs = previous.beliefs if previous else {}
        diff = {
            "added": {k: v for k, v in current.items() if k not in prev_beliefs},
            "removed": {k: prev_beliefs[k] for k in prev_beliefs if k not in current},
            "changed": {k: {"from": prev_beliefs[k], "to": current[k]}
                        for k in current if k in prev_beliefs and current[k] != prev_beliefs[k]},
        }
        new_events = [
            {"event_id": e.id, "source": e.source, "occurred_at": e.occurred_at.isoformat(), "text": e.text}
            for e in self.events.entity_events_after(entity_id, previous.through_seq if previous else 0)
        ]

        if persist:
            self.builds.add(ContextBuild(
                id=new_id("ctxb"), entity_id=entity_id, built_at=now, as_of=as_of,
                through_seq=through_seq, belief_hash=belief_hash, beliefs=current))
            self.session.commit()

        return {
            "entity_id": entity_id,
            "as_of": as_of.isoformat(),
            "has_previous_build": previous is not None,
            "previous_built_at": previous.built_at.isoformat() if previous else None,
            "unchanged": previous is not None and previous.belief_hash == belief_hash,
            "belief_hash": belief_hash,
            "through_seq": through_seq,
            "changes": diff,
            "new_events_since_last": new_events,
        }
