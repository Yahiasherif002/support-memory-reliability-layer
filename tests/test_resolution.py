"""Unit tests for the reliability-aware resolver (no DB)."""

from __future__ import annotations

from app.domain.enums import Polarity, Reliability, Source
from app.services.belief_resolver import resolve
from tests.helpers import aware, make_fact

AS_OF = aware(2026, 6, 18)


def test_reliability_beats_recency_and_authority():
    # Newer, but lower reliability — must still lose to the high-reliability contract.
    starter = make_fact(value="Starter", source=Source.CRM, reliability=Reliability.MEDIUM, observed_at=aware(2026, 4, 10))
    enterprise = make_fact(value="Enterprise Support", source=Source.CONTRACT, reliability=Reliability.HIGH, observed_at=aware(2026, 4, 2))
    res = resolve("e", "plan_tier", [starter, enterprise], AS_OF)
    assert res.current_value == "Enterprise Support"
    assert res.is_contradicted is True
    assert any(s.rule == "reliability" for s in res.trace)


def test_explicit_correction_supersedes_same_reliability():
    s42 = make_fact(value=42, attribute="seats", source=Source.AGENT_NOTE, reliability=Reliability.MEDIUM, observed_at=aware(2026, 4, 4, 10))
    s48 = make_fact(value=48, attribute="seats", source=Source.EMAIL, reliability=Reliability.MEDIUM, observed_at=aware(2026, 4, 4, 10), is_correction=True)
    res = resolve("e", "seats", [s42, s48], AS_OF)
    assert res.current_value == 48
    assert any(s.rule == "correction" for s in res.trace)


def test_recency_breaks_ties_within_a_reliability():
    a = make_fact(value="whatsapp", attribute="contact_preference", reliability=Reliability.MEDIUM, observed_at=aware(2026, 4, 1))
    b = make_fact(value="email", attribute="contact_preference", reliability=Reliability.MEDIUM, observed_at=aware(2026, 5, 1))
    res = resolve("e", "contact_preference", [a, b], AS_OF)
    assert res.current_value == "email"
    assert any(s.rule == "recency" for s in res.trace)


def test_corroboration_raises_confidence():
    facts = [make_fact(value="x", source=Source.CHAT, reliability=Reliability.LOW, confidence=0.3,
                       observed_at=aware(2026, m, 1), fact_id=f"f{m}") for m in range(1, 6)]
    res = resolve("e", "plan_tier", facts, AS_OF)
    assert res.confidence > 0.8 and "noisy-OR" in res.confidence_basis


def test_recent_retraction_removes_value_regardless_of_authority():
    asserted = make_fact(value="email", attribute="contact_preference", source=Source.CONTRACT,
                         reliability=Reliability.HIGH, observed_at=aware(2026, 1, 1))
    retract = make_fact(value="email", attribute="contact_preference", source=Source.CHAT,
                        reliability=Reliability.LOW, observed_at=aware(2026, 3, 1), polarity=Polarity.RETRACT)
    res = resolve("e", "contact_preference", [asserted, retract], AS_OF)
    assert res.current_value is None


def test_temporal_as_of():
    jan = make_fact(value="Starter", observed_at=aware(2026, 1, 1))
    jun = make_fact(value="Pro", observed_at=aware(2026, 6, 1))
    facts = [jan, jun]
    assert resolve("e", "plan_tier", facts, aware(2026, 3, 1)).current_value == "Starter"
    assert resolve("e", "plan_tier", facts, aware(2026, 6, 18)).current_value == "Pro"


def test_staleness_flag():
    old = make_fact(value="whatsapp", attribute="contact_preference", observed_at=aware(2024, 1, 1))
    assert resolve("e", "contact_preference", [old], AS_OF).is_stale is True
