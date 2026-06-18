"""Layer 5 — entity-scoped memory & cautious identity.

Scope is the assignment's explicit ``(entity_type, entity_id)`` — no inference.
``related_entity_ids`` become edges in ``entity_relations``. Identity *ambiguity*
is a separate, non-destructive signal: two ``contact`` entities asserting the same
email are surfaced as a candidate and **never merged**.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.hashing import sha256_hex
from app.core.ids import deterministic_id
from app.db.models import Entity, EntityRelation, IdentityCandidate, RawEvent
from app.db.repositories import EntityRepository, FactRepository, IdentityRepository
from app.domain.enums import EntityType


@dataclass
class ScopeResult:
    entity: Entity
    created: bool
    related: list[str] = field(default_factory=list)

    @property
    def decision(self) -> dict:
        return {"resolved_entity_id": self.entity.id, "entity_type": self.entity.entity_type,
                "created": self.created, "related_entity_ids": self.related}


class IdentityService:
    def __init__(self, entities: EntityRepository, identities: IdentityRepository, facts: FactRepository) -> None:
        self.entities = entities
        self.identities = identities
        self.facts = facts

    def scope(self, event: RawEvent) -> ScopeResult:
        entity = self.entities.get(event.entity_id)
        created = False
        if entity is None:
            entity = self.entities.add(Entity(
                id=event.entity_id, entity_type=event.entity_type, display_name=self._name(event),
                created_at=event.received_at, created_from_event_id=event.id))
            created = True
        elif entity.display_name is None and self._name(event):
            entity.display_name = self._name(event)

        related: list[str] = []
        for rid in (event.related_entity_ids or []):
            if rid and rid != entity.id:
                self.entities.add_relation(EntityRelation(
                    id=deterministic_id("rel", entity.id, rid), from_entity_id=entity.id,
                    to_entity_id=rid, via_event_id=event.id, created_at=event.received_at))
                related.append(rid)
        return ScopeResult(entity=entity, created=created, related=related)

    def detect_ambiguity(self, now: datetime) -> list[str]:
        """Contacts sharing a phone or email → an identity candidate (do not merge).

        On the assignment data this surfaces M. Salem / Omar (shared phone), who are
        plausibly different people on different accounts — exactly the case where a
        merge must be human-reviewed."""
        candidate_ids: list[str] = []
        for attribute in ("phone", "email"):
            for value_hash, entity_ids in self.facts.shared_values(attribute, EntityType.CONTACT).items():
                if len(entity_ids) < 2:
                    continue
                for i in range(len(entity_ids)):
                    for j in range(i + 1, len(entity_ids)):
                        candidate_ids.append(self._candidate(entity_ids[i], entity_ids[j], attribute, value_hash, now))
        return candidate_ids

    def _candidate(self, a: str, b: str, attribute: str, value_hash: str, now: datetime) -> str:
        lo, hi = sorted([a, b])
        reason = f"shared_{attribute}"
        dedupe_key = sha256_hex([lo, hi, reason, value_hash])
        row, _ = self.identities.add_idempotent(IdentityCandidate(
            id=deterministic_id("idc", dedupe_key), entity_id_a=lo, entity_id_b=hi, reason=reason,
            score=0.7, evidence={"value_hash": value_hash}, status="pending_review",
            detected_at=now, dedupe_key=dedupe_key))
        return row.id

    @staticmethod
    def _name(event: RawEvent) -> str | None:
        p = event.payload or {}
        return p.get("account_name") or p.get("name") or p.get("contact_name") or p.get("display_name")
