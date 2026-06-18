"""Layer 7 — explainability.

Belief explanations go through the **same** ``BeliefResolutionEngine`` as the
context builder (so the two endpoints can never disagree), then dress the result
with provenance: every fact for the attribute, the rule that eliminated each
loser, and the evidence chain back to raw events and payload fields.

``explain_event`` adds lineage beyond belief resolution: how an event was
classified for idempotency, which entity it resolved to and why (the identity
decision), and what it produced.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import Clock, ensure_utc
from app.db.models import Fact, RawEvent
from app.db.repositories import EntityRepository, EventRepository, FactRepository
from app.domain.explain import (
    BeliefExplanation,
    EntityExplanation,
    EventExplanation,
    EvidenceItem,
    FactExplanation,
)
from app.services.belief_resolver import BeliefResolutionEngine


class ExplainabilityService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self.clock = clock
        self.entities = EntityRepository(session)
        self.facts = FactRepository(session)
        self.events = EventRepository(session)
        self.engine = BeliefResolutionEngine(self.facts, clock)

    def explain_attribute(
        self, entity_id: str, attribute: str, as_of: datetime | None = None
    ) -> BeliefExplanation | None:
        if self.entities.get(entity_id) is None:
            return None
        facts = self.facts.list_for_entity_attribute(entity_id, attribute)
        if not facts:
            return None

        at = ensure_utc(as_of) if as_of else self.clock.now()
        res = self.engine.reconstruct(entity_id, attribute, at)  # SAME engine as context

        verdict_by_id = {v.fact_id: v for v in res.verdicts}
        considered = set(res.considered_fact_ids)
        evidence_map = self.facts.evidence_for_facts([f.id for f in facts])
        event_cache: dict[str, RawEvent | None] = {}

        fact_explanations = [
            self._explain_fact(f, res.winning_fact_id, verdict_by_id, considered, evidence_map, event_cache)
            for f in facts
        ]

        return BeliefExplanation(
            entity_id=entity_id, attribute=attribute, as_of=at,
            current_value=res.current_value, confidence=res.confidence,
            confidence_basis=res.confidence_basis, is_stale=res.is_stale,
            is_contradicted=res.is_contradicted, policy=res.policy,
            winning_fact_id=res.winning_fact_id, resolution_trace=res.trace,
            facts=fact_explanations,
        )

    def explain_entity(self, entity_id: str, as_of: datetime | None = None) -> EntityExplanation | None:
        if self.entities.get(entity_id) is None:
            return None
        at = ensure_utc(as_of) if as_of else self.clock.now()
        beliefs = []
        for attribute in sorted(self.facts.distinct_attributes(entity_id)):
            explanation = self.explain_attribute(entity_id, attribute, at)
            if explanation is not None:
                beliefs.append(explanation)
        return EntityExplanation(entity_id=entity_id, as_of=at, beliefs=beliefs)

    def explain_event(self, event_id: str) -> EventExplanation | None:
        event = self.events.get(event_id)
        if event is None:
            return None
        proc = self.events.get_processing(event_id)
        return EventExplanation(
            event_id=event.id, source=event.source, entity_type=event.entity_type,
            actor=event.actor, reliability=event.reliability,
            occurred_at=event.occurred_at, received_at=event.received_at,
            dedup_status=event.dedup_status,
            processing_status=proc.status if proc else None,
            entity_id=proc.entity_id if proc else None,
            facts_created=proc.facts_created if proc else 0,
            extractor_versions=proc.extractor_versions if proc else {},
            decision=proc.decision if proc else {},
            note=proc.note if proc else None,
        )

    def _explain_fact(self, fact, winning_fact_id, verdict_by_id, considered, evidence_map, event_cache):
        is_winner = fact.id == winning_fact_id
        eliminated_by: str | None = None
        if not is_winner:
            verdict = verdict_by_id.get(fact.id)
            if verdict is not None:
                eliminated_by = verdict.eliminated_by
            elif fact.id not in considered:
                eliminated_by = "not_valid_at_as_of"
            else:
                eliminated_by = "superseded_within_value_group"

        evidence = []
        for edge in evidence_map.get(fact.id, []):
            if edge.source_event_id not in event_cache:
                event_cache[edge.source_event_id] = self.events.get(edge.source_event_id)
            event = event_cache[edge.source_event_id]
            evidence.append(
                EvidenceItem(
                    event_id=edge.source_event_id,
                    source=event.source if event else "unknown",
                    reliability=event.reliability if event else None,
                    actor=event.actor if event else None,
                    occurred_at=event.occurred_at if event else fact.observed_at,
                    relation=edge.relation, locator=edge.locator or {},
                    payload_excerpt=_locate(event.payload if event else None, edge.locator),
                    text=event.text if event else None,
                )
            )

        return FactExplanation(
            fact_id=fact.id, attribute=fact.attribute, value=fact.value, source=fact.source,
            reliability=fact.reliability,
            confidence=fact.confidence, polarity=fact.polarity, valid_from=fact.valid_from,
            valid_to=fact.valid_to, observed_at=fact.observed_at, recorded_at=fact.recorded_at,
            is_winner=is_winner, eliminated_by=eliminated_by,
            extractor=f"{fact.extractor_name}@{fact.extractor_version}", evidence=evidence,
        )


def _locate(payload: dict | None, locator: dict | None) -> Any:
    if not payload or not locator:
        return None
    field = locator.get("field")
    if not field:
        return None
    if field in payload:
        return payload[field]
    match = re.fullmatch(r"(\w+)\[(\d+)\]", field)
    if match and match.group(1) in payload:
        seq = payload[match.group(1)]
        idx = int(match.group(2))
        if isinstance(seq, list) and 0 <= idx < len(seq):
            return seq[idx]
    return None
