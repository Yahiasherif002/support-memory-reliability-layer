"""Data-access layer. Repositories flush but never commit; the service layer owns
transaction boundaries."""

from app.db.repositories.beliefs import BeliefRepository
from app.db.repositories.context_builds import ContextBuildRepository
from app.db.repositories.contradictions import ContradictionRepository
from app.db.repositories.entities import EntityRepository
from app.db.repositories.events import EventRepository
from app.db.repositories.facts import FactRepository
from app.db.repositories.identity import IdentityRepository

__all__ = [
    "BeliefRepository",
    "ContextBuildRepository",
    "ContradictionRepository",
    "EntityRepository",
    "EventRepository",
    "FactRepository",
    "IdentityRepository",
]
