"""Seed a demo scenario.

Loads one rich customer plus a second customer that shares an email, exercising
every reliability feature at once:

* a **contradiction** (Contracts says "enterprise", CRM later says "pro");
* a **stale** belief (a contact preference from 2024);
* a 3-way contact-preference conflict across CRM / chat / agent-notes;
* a **duplicate replay** (ignored) and an **idempotency conflict** (flagged);
* an **identity ambiguity** (an event linking two customers via a shared email).

Run with:  uv run python scripts/seed.py
The script resets the demo database so each run starts clean.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.clock import SystemClock
from app.core.config import get_settings
from app.db.base import Base
from app.db.repositories import (
    ContradictionRepository,
    EntityRepository,
    FactRepository,
    IdentityRepository,
)
from app.db.session import build_engine, create_all, make_session_factory
from app.domain.enums import EntityType, EventType, IdentifierType, Source
from app.domain.events import IdentifierIn, IngestEnvelope, SubjectHint
from app.services.ingest_service import IngestService


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def env(source, event_type, payload, *, key, occurred, identifiers, entity_type=None, display_name=None):
    return IngestEnvelope(
        source=source,
        event_type=event_type,
        idempotency_key=key,
        occurred_at=occurred,
        subject_hint=SubjectHint(
            entity_type=entity_type,
            display_name=display_name,
            identifiers=[IdentifierIn(id_type=t, id_value=v) for t, v in identifiers],
        ),
        payload=payload,
    )


def main() -> None:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    # Reset so the demo is reproducible.
    Base.metadata.drop_all(engine)
    create_all(engine)

    session = make_session_factory(engine)()
    svc = IngestService(session, SystemClock())

    acme = [(IdentifierType.CRM_ID, "C-1000")]

    envelopes = [
        # --- the authoritative truth, and a later CRM disagreement -> contradiction
        env(Source.CONTRACTS, EventType.CONTRACT_SIGNED,
            {"plan": "enterprise", "term_months": 24, "renewal_date": "2027-02-01"},
            key="contract-1", occurred=dt("2026-02-01"),
            identifiers=acme + [(IdentifierType.CONTRACT_ID, "K-55")],
            entity_type=EntityType.CUSTOMER, display_name="Acme Inc"),
        env(Source.CRM, EventType.PLAN_CHANGED, {"plan": "pro"},
            key="crm-plan-1", occurred=dt("2026-03-01"), identifiers=acme),

        # --- a stale contact preference, then a newer (but lower-authority) one -> conflict + staleness
        env(Source.CRM, EventType.CONTACT_PREFERENCE_SET, {"channel": "email"},
            key="crm-pref-1", occurred=dt("2024-01-10"), identifiers=acme),
        env(Source.CHAT, EventType.CHAT_MESSAGE, {"declared_contact_preference": "phone"},
            key="chat-1", occurred=dt("2026-05-01"), identifiers=acme),
        env(Source.AGENT_NOTES, EventType.AGENT_NOTE_ADDED,
            {"observations": [{"attribute": "contact_preference", "value": "sms", "confidence": 0.8}]},
            key="note-1", occurred=dt("2026-06-15"), identifiers=acme),

        # --- ordinary recent activity
        env(Source.INTERNAL, EventType.ACCOUNT_STATUS_CHANGED, {"status": "active"},
            key="internal-1", occurred=dt("2026-06-01"), identifiers=acme),
        env(Source.EMAIL, EventType.EMAIL_RECEIVED,
            {"sentiment": "frustrated", "reason": "billing question about renewal"},
            key="email-1", occurred=dt("2026-06-10"), identifiers=acme),

        # --- idempotency: an exact replay (ignored) and a key-collision (flagged)
        env(Source.CRM, EventType.PLAN_CHANGED, {"plan": "pro"},
            key="crm-plan-1", occurred=dt("2026-03-01"), identifiers=acme),
        env(Source.CRM, EventType.PLAN_CHANGED, {"plan": "free"},
            key="crm-plan-1", occurred=dt("2026-03-01"), identifiers=acme),

        # --- a second customer that owns a shared email
        env(Source.CRM, EventType.IDENTITY_OBSERVED, {},
            key="crm-id-bob", occurred=dt("2026-04-01"),
            identifiers=[(IdentifierType.CRM_ID, "C-2000"), (IdentifierType.EMAIL, "shared@acme.com")],
            entity_type=EntityType.CUSTOMER, display_name="Bob (Acme)"),
        # --- an event that links Acme (C-1000) and that shared email -> identity ambiguity
        env(Source.EMAIL, EventType.EMAIL_RECEIVED, {"reason": "forwarded thread"},
            key="email-2", occurred=dt("2026-06-12"),
            identifiers=[(IdentifierType.CRM_ID, "C-1000"), (IdentifierType.EMAIL, "shared@acme.com")]),
    ]

    main_entity_id = None
    for envelope in envelopes:
        result = svc.ingest(envelope)
        if envelope.idempotency_key == "contract-1":
            main_entity_id = result.entity_id

    session.close()

    read = make_session_factory(engine)()
    facts = FactRepository(read)
    entities = EntityRepository(read)
    contradictions = ContradictionRepository(read)
    identities = IdentityRepository(read)

    all_entities = entities.list_all()
    total_facts = sum(len(facts.list_for_entity(e.id)) for e in all_entities)
    open_conflicts = contradictions.list(status="open")
    candidates = identities.list()

    print("\n=== Support Memory seeded ===")
    print(f"database         : {settings.database_url}")
    print(f"entities         : {len(all_entities)}")
    print(f"facts            : {total_facts}")
    print(f"contradictions   : {len(open_conflicts)} open")
    print(f"identity candidates: {len(candidates)}")
    print(f"\nMain customer entity_id: {main_entity_id}")
    print("\nTry:")
    print(f"  GET /v1/entities/{main_entity_id}/context")
    print(f"  GET /v1/entities/{main_entity_id}/explain?attribute=plan_tier")
    print(f"  GET /v1/entities/{main_entity_id}/explain?attribute=contact_preference")
    print("  GET /v1/conflicts")
    read.close()


if __name__ == "__main__":
    main()
