"""Mid-test scope change: 'what changed since the last context build?'"""

from __future__ import annotations


def test_baseline_then_unchanged(seeded_client):
    first = seeded_client.get("/v1/entities/acct_helios_945/context/diff").json()
    assert first["has_previous_build"] is False
    assert "plan_tier" in first["changes"]["added"]

    second = seeded_client.get("/v1/entities/acct_helios_945/context/diff").json()
    assert second["has_previous_build"] is True
    assert second["unchanged"] is True
    assert second["changes"]["added"] == {} and second["changes"]["changed"] == {}


def test_detects_a_new_change(seeded_client):
    seeded_client.get("/v1/entities/acct_helios_945/context/diff")  # establish baseline
    seeded_client.post("/v1/events:ingest", json={
        "event_id": "evt-new", "idempotency_key": "idem-new", "occurred_at": "2026-05-01T00:00:00Z",
        "source": "contract", "actor": "importer", "entity_type": "account", "entity_id": "acct_helios_945",
        "related_entity_ids": [], "reliability": "high", "text": "Plan downgraded to Pro.", "payload": {"plan": "Pro"},
    })
    diff = seeded_client.get("/v1/entities/acct_helios_945/context/diff").json()
    assert diff["unchanged"] is False
    assert "plan_tier" in diff["changes"]["changed"]
    assert any(e["event_id"] == "evt-new" for e in diff["new_events_since_last"])
