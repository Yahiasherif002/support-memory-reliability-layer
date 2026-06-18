"""Facts (immutable) + evidence edges + batch loaders + an ambiguity index."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Entity, Fact, FactEvidence, RawEvent


class FactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_idempotent(self, fact: Fact) -> tuple[Fact, bool]:
        existing = self.get_by_dedupe_key(fact.dedupe_key)
        if existing is not None:
            return existing, False
        self.session.add(fact)
        self.session.flush()
        return fact, True

    def get(self, fact_id: str) -> Fact | None:
        return self.session.get(Fact, fact_id)

    def get_many(self, fact_ids: list[str]) -> dict[str, Fact]:
        if not fact_ids:
            return {}
        rows = self.session.execute(select(Fact).where(Fact.id.in_(fact_ids))).scalars().all()
        return {f.id: f for f in rows}

    def get_by_dedupe_key(self, dedupe_key: str) -> Fact | None:
        return self.session.execute(select(Fact).where(Fact.dedupe_key == dedupe_key)).scalar_one_or_none()

    def list_for_entity_attribute(self, entity_id: str, attribute: str) -> list[Fact]:
        return list(self.session.execute(
            select(Fact).where(Fact.entity_id == entity_id, Fact.attribute == attribute)
            .order_by(Fact.observed_at, Fact.recorded_at)
        ).scalars().all())

    def list_for_entity(self, entity_id: str) -> list[Fact]:
        return list(self.session.execute(
            select(Fact).where(Fact.entity_id == entity_id)
            .order_by(Fact.attribute, Fact.observed_at, Fact.recorded_at)
        ).scalars().all())

    def list_recent_for_entity(self, entity_id: str, limit: int) -> list[Fact]:
        return list(self.session.execute(
            select(Fact).where(Fact.entity_id == entity_id)
            .order_by(Fact.observed_at.desc(), Fact.recorded_at.desc()).limit(limit)
        ).scalars().all())

    def distinct_attributes(self, entity_id: str) -> list[str]:
        return list(self.session.execute(
            select(Fact.attribute).where(Fact.entity_id == entity_id).distinct()
        ).scalars().all())

    def high_water_seq(self, entity_id: str, attribute: str) -> int:
        return self.session.execute(
            select(func.max(RawEvent.seq)).select_from(Fact)
            .join(RawEvent, RawEvent.id == Fact.source_event_id)
            .where(Fact.entity_id == entity_id, Fact.attribute == attribute)
        ).scalar() or 0

    def shared_values(self, attribute: str, entity_type: str) -> dict[str, list[str]]:
        """value_hash -> distinct entity ids (of a type) asserting that value.

        A value owned by >1 entity of type ``contact`` is an identity-ambiguity
        signal (e.g. two contacts with the same email)."""
        rows = self.session.execute(
            select(Fact.value_hash, Fact.entity_id).join(Entity, Entity.id == Fact.entity_id)
            .where(Fact.attribute == attribute, Fact.polarity == "assert", Entity.entity_type == entity_type)
        ).all()
        out: dict[str, set[str]] = {}
        for value_hash, entity_id in rows:
            out.setdefault(value_hash, set()).add(entity_id)
        return {vh: sorted(ids) for vh, ids in out.items()}

    # --- evidence --------------------------------------------------------
    def add_evidence(self, evidence: FactEvidence) -> FactEvidence:
        self.session.add(evidence)
        self.session.flush()
        return evidence

    def list_evidence(self, fact_id: str) -> list[FactEvidence]:
        return list(self.session.execute(
            select(FactEvidence).where(FactEvidence.fact_id == fact_id)
        ).scalars().all())

    def evidence_for_facts(self, fact_ids: list[str]) -> dict[str, list[FactEvidence]]:
        if not fact_ids:
            return {}
        rows = self.session.execute(select(FactEvidence).where(FactEvidence.fact_id.in_(fact_ids))).scalars().all()
        out: dict[str, list[FactEvidence]] = {fid: [] for fid in fact_ids}
        for edge in rows:
            out.setdefault(edge.fact_id, []).append(edge)
        return out
