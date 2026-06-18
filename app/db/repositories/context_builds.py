"""Context-build history (for the 'what changed since last build?' diff)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ContextBuild


class ContextBuildRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest(self, entity_id: str) -> ContextBuild | None:
        return self.session.execute(
            select(ContextBuild).where(ContextBuild.entity_id == entity_id)
            .order_by(ContextBuild.built_at.desc()).limit(1)
        ).scalar_one_or_none()

    def add(self, build: ContextBuild) -> ContextBuild:
        self.session.add(build)
        self.session.flush()
        return build
