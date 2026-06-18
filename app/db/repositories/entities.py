"""Entities (keyed by the assignment entity_id) and their relations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Entity, EntityRelation


class EntityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, entity_id: str) -> Entity | None:
        return self.session.get(Entity, entity_id)

    def add(self, entity: Entity) -> Entity:
        self.session.add(entity)
        self.session.flush()
        return entity

    def list_all(self) -> list[Entity]:
        return list(self.session.execute(select(Entity).order_by(Entity.id)).scalars().all())

    # --- relations (related_entity_ids graph) ---------------------------
    def add_relation(self, relation: EntityRelation) -> EntityRelation:
        existing = self.session.execute(
            select(EntityRelation).where(
                EntityRelation.from_entity_id == relation.from_entity_id,
                EntityRelation.to_entity_id == relation.to_entity_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        self.session.add(relation)
        self.session.flush()
        return relation

    def related_ids(self, entity_id: str) -> list[str]:
        """Both directions: ids this entity points to, and ids that point to it."""
        out = set(
            self.session.execute(
                select(EntityRelation.to_entity_id).where(EntityRelation.from_entity_id == entity_id)
            ).scalars().all()
        )
        out.update(
            self.session.execute(
                select(EntityRelation.from_entity_id).where(EntityRelation.to_entity_id == entity_id)
            ).scalars().all()
        )
        return sorted(out)
