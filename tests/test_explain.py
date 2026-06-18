"""Evidence-linked explainability (belief lineage + event lineage)."""

from __future__ import annotations


def test_belief_explanation_traces_to_evidence(seeded_client):
    exp = seeded_client.get("/v1/entities/acct_helios_945/explain", params={"attribute": "plan_tier"}).json()
    assert exp["current_value"] == "Enterprise Support"

    winner = next(f for f in exp["facts"] if f["is_winner"])
    assert winner["reliability"] == "high"
    assert winner["evidence"][0]["event_id"] == "evt-1003"  # the signed addendum

    losers = [f for f in exp["facts"] if not f["is_winner"]]
    assert losers and all(loser["eliminated_by"] for loser in losers)
    assert any(step["rule"] == "reliability" for step in exp["resolution_trace"])


def test_event_explanation_shows_identity_and_idempotency_lineage(seeded_client):
    ev = seeded_client.get("/v1/events/evt-1003/explain").json()
    assert ev["entity_id"] == "acct_helios_945"
    assert ev["source"] == "contract" and ev["reliability"] == "high"
    assert ev["dedup_status"] == "new"
    assert ev["decision"]["resolved_entity_id"] == "acct_helios_945"
    assert ev["facts_created"] >= 1
