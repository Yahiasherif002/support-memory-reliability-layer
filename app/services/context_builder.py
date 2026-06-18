"""Layer 6 — context builder with policy isolation.

Beliefs come from the same ``BeliefResolutionEngine`` as explain (so they agree).
``applicable_policies`` are resolved **only** from policy entities related to this
account via ``entity_relations`` — a policy on another account can never appear here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.clock import Clock, ensure_utc
from app.core.config import get_settings
from app.db.models import Entity
from app.db.repositories import ContradictionRepository, EntityRepository, FactRepository, IdentityRepository
from app.domain.beliefs import Resolution
from app.domain.context import (
    ContextActivity, ContextBelief, ContextPack, ContextPolicy, IdentityWarning, ProvenanceRef,
)
from app.domain.entities import EntityView
from app.domain.enums import EntityType
from app.policies.attribute_importance import importance
from app.policies.attributes import Attr
from app.services.belief_resolver import BeliefResolutionEngine
from app.services.conflict_service import contradiction_to_item

RECENCY_HALF_LIFE_DAYS = 180.0
STALE_PENALTY = 0.4
MAX_RECENT_ACTIVITY = 8


class ContextBuilder:
    def __init__(self, session: Session, clock: Clock) -> None:
        self.clock = clock
        self.entities = EntityRepository(session)
        self.facts = FactRepository(session)
        self.contradictions = ContradictionRepository(session)
        self.identities = IdentityRepository(session)
        self.engine = BeliefResolutionEngine(self.facts, clock)

    def build(self, entity_id: str, *, budget: int | None = None, as_of: datetime | None = None) -> ContextPack | None:
        entity = self.entities.get(entity_id)
        if entity is None:
            return None
        now = self.clock.now()
        as_of = ensure_utc(as_of) if as_of else now
        budget = budget or get_settings().default_context_budget

        resolutions = self.engine.reconstruct_entity(entity_id, as_of)
        winners = self.facts.get_many([r.winning_fact_id for r in resolutions.values() if r.winning_fact_id])
        evidence_map = self.facts.evidence_for_facts(list(winners.keys()))

        scored: list[tuple[float, str, Resolution]] = []
        for attribute, res in resolutions.items():
            if res.current_value is None or attribute == Attr.POLICY_RULE:
                continue  # a policy entity's own rule is surfaced via applicable_policies
            scored.append((self._salience(attribute, res, as_of), attribute, res))
        scored.sort(key=lambda t: (-t[0], t[1]))
        chosen, dropped = scored[:budget], scored[budget:]

        beliefs_out = [self._belief(entity_id, a, r, s, winners, evidence_map) for s, a, r in chosen]
        applicable_policies = self._policies_for(entity_id, as_of)

        notes: list[str] = []
        if dropped:
            notes.append(f"{len(dropped)} lower-salience belief(s) omitted by budget.")
        if any(r.is_contradicted for _s, _a, r in chosen):
            notes.append("Some beliefs are contradicted — see open_contradictions.")
        identity_warnings = self._identity_warnings(entity_id)
        if identity_warnings:
            notes.append(f"{len(identity_warnings)} identity ambiguity(ies): do NOT merge without review.")

        return ContextPack(
            entity=self._entity_view(entity), generated_at=now, as_of=as_of, budget=budget,
            beliefs=beliefs_out, applicable_policies=applicable_policies,
            open_contradictions=[contradiction_to_item(c) for c in self.contradictions.list(entity_id=entity_id, status="open")],
            identity_warnings=identity_warnings, recent_activity=self._recent(entity_id), notes=notes)

    def _belief(self, entity_id, attribute, res, salience, winners, evidence_map) -> ContextBelief:
        winner = winners.get(res.winning_fact_id)
        reliability = winner.reliability if winner else None
        return ContextBelief(
            attribute=attribute, value=res.current_value, confidence=res.confidence, reliability=reliability,
            is_stale=res.is_stale, is_contradicted=res.is_contradicted, salience=salience,
            provenance=ProvenanceRef(
                fact_id=res.winning_fact_id, reliability=reliability,
                event_ids=[e.source_event_id for e in evidence_map.get(res.winning_fact_id, [])],
                explain=f"/v1/entities/{entity_id}/explain?attribute={attribute}"))

    def _policies_for(self, entity_id: str, as_of: datetime) -> list[ContextPolicy]:
        out: list[ContextPolicy] = []
        for related_id in self.entities.related_ids(entity_id):
            related = self.entities.get(related_id)
            if related is None or related.entity_type != EntityType.POLICY:
                continue
            res = self.engine.reconstruct(related_id, Attr.POLICY_RULE, as_of)
            if res.current_value is None:
                continue
            winner = self.facts.get(res.winning_fact_id) if res.winning_fact_id else None
            value = res.current_value if isinstance(res.current_value, dict) else {"name": "policy", "rule": res.current_value}
            out.append(ContextPolicy(
                policy_entity_id=related_id, name=value.get("name", "policy"), rule=value.get("rule"),
                reliability=winner.reliability if winner else None,
                provenance=ProvenanceRef(
                    fact_id=res.winning_fact_id,
                    event_ids=[e.source_event_id for e in self.facts.list_evidence(res.winning_fact_id)] if res.winning_fact_id else [],
                    explain=f"/v1/entities/{related_id}/explain?attribute={Attr.POLICY_RULE}")))
        return out

    def _salience(self, attribute: str, res: Resolution, as_of: datetime) -> float:
        age_days = max(0.0, (as_of - res.winner_observed_at).total_seconds() / 86400.0) if res.winner_observed_at else 0.0
        recency = 1.0 / (1.0 + age_days / RECENCY_HALF_LIFE_DAYS)
        stale_factor = STALE_PENALTY if res.is_stale else 1.0
        return round(importance(attribute) * (0.5 + 0.5 * res.confidence) * recency * stale_factor, 4)

    def _identity_warnings(self, entity_id: str) -> list[IdentityWarning]:
        warnings = []
        for c in self.identities.list(entity_id=entity_id, status="pending_review"):
            other = c.entity_id_b if c.entity_id_a == entity_id else c.entity_id_a
            warnings.append(IdentityWarning(candidate_id=c.id, other_entity_id=other, reason=c.reason, score=c.score, status=c.status))
        return warnings

    def _recent(self, entity_id: str) -> list[ContextActivity]:
        return [ContextActivity(fact_id=f.id, attribute=f.attribute, value=f.value, source=f.source,
                                reliability=f.reliability, observed_at=f.observed_at, event_id=f.source_event_id)
                for f in self.facts.list_recent_for_entity(entity_id, MAX_RECENT_ACTIVITY)]

    def _entity_view(self, entity: Entity) -> EntityView:
        return EntityView(id=entity.id, entity_type=entity.entity_type, display_name=entity.display_name,
                          created_at=entity.created_at, related_entity_ids=self.entities.related_ids(entity.id))
