"""Load the assignment's 20-event dataset (data/seed_events.json) UNMODIFIED.

    uv run python scripts/load_seed.py

Resets the configured database, ingests every Memory Event verbatim, then prints a
summary and short answers to the five business questions.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.clock import SystemClock
from app.core.config import get_settings
from app.db.base import Base
from app.db.repositories import ContradictionRepository, EntityRepository, FactRepository, IdentityRepository
from app.db.session import build_engine, create_all, make_session_factory
from app.domain.events import MemoryEvent
from app.services.ingest_service import IngestService

DATA = Path(__file__).resolve().parent.parent / "data" / "seed_events.json"


def main() -> None:
    settings = get_settings()
    # Start clean: drop the local sqlite file if present (avoids FK-ordered drops).
    if settings.database_url.startswith("sqlite:///"):
        db_path = Path(settings.database_url.replace("sqlite:///", ""))
        if db_path.exists():
            db_path.unlink()
    engine = build_engine(settings.database_url)
    create_all(engine)
    session = make_session_factory(engine)()
    svc = IngestService(session, SystemClock())

    events = json.loads(DATA.read_text(encoding="utf-8"))
    results = [svc.ingest(MemoryEvent(**e)) for e in events]

    entities = EntityRepository(session)
    facts = FactRepository(session)
    contradictions = ContradictionRepository(session)
    identities = IdentityRepository(session)

    n_facts = sum(len(facts.list_for_entity(e.id)) for e in entities.list_all())
    print("\n=== Loaded the assignment dataset ===")
    print(f"events ingested : {len(results)}")
    print(f"entities        : {len(entities.list_all())}")
    print(f"facts           : {n_facts}")
    print(f"contradictions  : {len(contradictions.list(status='open'))} open "
          f"({len(contradictions.list(kind='idempotency_conflict'))} idempotency)")
    print(f"identity cands  : {len(identities.list())}")
    print("\nTry:")
    print("  GET /v1/entities/acct_helios_945/context")
    print("  GET /v1/entities/acct_helios_945/explain?attribute=plan_tier")
    print("  GET /v1/entities/acct_nova_945/context        (shows the privacy policy)")
    print("  GET /v1/conflicts")
    print("  GET /v1/entities/acct_helios_945/context/diff")
    session.close()


if __name__ == "__main__":
    main()
