"""Event-sourcing guarantees: rebuild-from-empty is identical; replay is deterministic."""

from __future__ import annotations

from sqlalchemy import select

from app.core.clock import FixedClock
from app.db.models import Belief, Fact
from app.db.repositories import FactRepository
from app.services.belief_resolver import BeliefResolutionEngine
from app.services.replay_engine import ReplayEngine
from tests.helpers import aware


def _beliefs(session):
    return {b.id: (b.entity_id, b.attribute, b.current_value, b.winning_fact_id, b.is_contradicted)
            for b in session.execute(select(Belief)).scalars().all()}


def test_rebuild_from_empty_is_byte_identical(loaded, session, clock):
    before = _beliefs(session)
    facts_before = {f.id for f in session.execute(select(Fact)).scalars().all()}
    assert before and facts_before

    summary = ReplayEngine(session, clock).rebuild_all()
    assert summary["events_processed"] == 19  # the 19 NEW events (evt-1009 was a conflict)

    assert _beliefs(session) == before
    assert {f.id for f in session.execute(select(Fact)).scalars().all()} == facts_before


def test_replay_determinism_under_advanced_clock(loaded, session):
    facts = FactRepository(session)
    as_of = aware(2026, 6, 18)
    today = BeliefResolutionEngine(facts, FixedClock(aware(2026, 6, 18))).reconstruct_entity("acct_helios_945", as_of)
    future = BeliefResolutionEngine(facts, FixedClock(aware(2030, 1, 1))).reconstruct_entity("acct_helios_945", as_of)

    def norm(m):
        return {k: (r.current_value, r.winning_fact_id, r.is_contradicted, r.is_stale) for k, r in m.items()}

    assert norm(today) == norm(future)
