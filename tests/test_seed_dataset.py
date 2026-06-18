"""Ingest the exact 20-event assignment dataset and assert the key outcomes."""

from __future__ import annotations

from app.db.repositories import BeliefRepository, EntityRepository
from app.domain.enums import DedupStatus


def _value(session, entity_id, attribute):
    b = BeliefRepository(session).get(entity_id, attribute)
    return b.current_value["value"] if b and b.current_value else None


def test_all_twenty_events_ingest(loaded):
    assert len(loaded) == 20
    statuses = [r.dedup_status for r in loaded]
    # evt-1009 reuses idem-1008 with a different body -> exactly one conflict; the rest are new.
    assert statuses.count(DedupStatus.IDEMPOTENCY_CONFLICT) == 1
    assert statuses.count(DedupStatus.NEW) == 19


def test_entities_scoped_by_assignment_id(loaded, session):
    er = EntityRepository(session)
    assert er.get("acct_helios_945").entity_type == "account"
    assert er.get("contact_mona_945").entity_type == "contact"
    assert er.get("ticket_h_945_p1").entity_type == "ticket"
    assert er.get("policy_nova_945_privacy").entity_type == "policy"


def test_helios_plan_is_enterprise_and_contradicted(loaded, session):
    belief = BeliefRepository(session).get("acct_helios_945", "plan_tier")
    assert belief.current_value["value"] == "Enterprise Support"
    assert belief.is_contradicted is True  # Starter vs Enterprise coexist


def test_ticket_seat_correction_wins(loaded, session):
    assert _value(session, "ticket_h_945_p1", "seats") == 48  # 48 corrected 42


def test_mona_preference_superseded_to_email(loaded, session):
    assert _value(session, "contact_mona_945", "contact_preference") == "email_only_except_p1"


def test_sla_and_support_extracted_for_helios(loaded, session):
    assert _value(session, "acct_helios_945", "support_tier") == "Enterprise"
    sla = _value(session, "acct_helios_945", "sla_target")
    assert sla == {"priority": "P1", "value": 2, "unit": "hours"}
