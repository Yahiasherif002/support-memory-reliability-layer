"""The five assignment 'starter questions to prove', over HTTP on the seed data."""

from __future__ import annotations


def test_q1_what_should_a_rep_know_before_calling_helios(seeded_client):
    ctx = seeded_client.get("/v1/entities/acct_helios_945/context").json()
    assert ctx["entity"]["display_name"] == "Helios Apps"
    attrs = {b["attribute"] for b in ctx["beliefs"]}
    assert {"plan_tier", "support_tier", "sla_target"} <= attrs
    # Every belief is evidence-linked.
    assert all(b["provenance"]["event_ids"] for b in ctx["beliefs"])


def test_q2_which_facts_changed_and_which_source_wins(seeded_client):
    exp = seeded_client.get("/v1/entities/acct_helios_945/explain", params={"attribute": "plan_tier"}).json()
    assert exp["current_value"] == "Enterprise Support"
    winner = next(f for f in exp["facts"] if f["is_winner"])
    assert winner["source"] == "contract" and winner["reliability"] == "high"
    assert {f["value"] for f in exp["facts"]} >= {"Starter", "Enterprise Support"}


def test_q3_account_policy_does_not_leak(seeded_client):
    helios = seeded_client.get("/v1/entities/acct_helios_945/context").json()
    nova = seeded_client.get("/v1/entities/acct_nova_945/context").json()
    assert helios["applicable_policies"] == []  # Nova's policy must not appear here
    assert any(p["policy_entity_id"] == "policy_nova_945_privacy" for p in nova["applicable_policies"])


def test_q4_duplicate_retries_and_idempotency_conflicts(seeded_client):
    conflicts = seeded_client.get("/v1/conflicts", params={"kind": "idempotency_conflict"}).json()
    assert len(conflicts) == 1
    assert conflicts[0]["refs"]["event_id_b"] == "evt-1009"
    assert conflicts[0]["refs"]["event_id_a"] == "evt-1008"


def test_q5_contacts_not_to_merge_without_review(seeded_client):
    conflicts = seeded_client.get("/v1/conflicts").json()
    candidates = [c for c in conflicts if c["type"] == "identity_candidate"]
    assert candidates
    pair = {candidates[0]["refs"]["entity_id_a"], candidates[0]["refs"]["entity_id_b"]}
    assert pair == {"contact_m_salem_945", "contact_omar_945"}  # shared phone, do not merge
