"""Generate sample_outputs/ from the assignment dataset (deterministic).

Uses an in-memory DB and a fixed clock so the committed samples are stable.

    uv run python scripts/generate_samples.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.clock import FixedClock
from app.main import create_app

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sample_outputs"
NOW = datetime(2026, 6, 18, tzinfo=timezone.utc)
HELIOS, NOVA = "acct_helios_945", "acct_nova_945"


def _write(name: str, payload) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote sample_outputs/{name}")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    app = create_app(database_url="sqlite://", clock=FixedClock(NOW))
    client = TestClient(app)
    events = json.loads((ROOT / "data" / "seed_events.json").read_text(encoding="utf-8"))
    ingest_results = [client.post("/v1/events:ingest", json=e).json() for e in events]

    helios_ctx = client.get(f"/v1/entities/{HELIOS}/context").json()
    nova_ctx = client.get(f"/v1/entities/{NOVA}/context").json()
    helios_plan = client.get(f"/v1/entities/{HELIOS}/explain", params={"attribute": "plan_tier"}).json()
    conflicts = client.get("/v1/conflicts").json()
    diff = client.get(f"/v1/entities/{HELIOS}/context/diff").json()

    _write("helios_context.json", helios_ctx)
    _write("helios_explain_plan.json", helios_plan)
    _write("nova_context.json", nova_ctx)
    _write("conflicts.json", conflicts)
    _write("helios_context_diff.json", diff)

    business_questions = {
        "1_what_should_a_rep_know_before_calling_helios": {
            "answer_source": "GET /v1/entities/acct_helios_945/context",
            "top_beliefs": [{"attribute": b["attribute"], "value": b["value"],
                             "reliability": b["reliability"], "is_contradicted": b["is_contradicted"]}
                            for b in helios_ctx["beliefs"]],
            "open_contradictions": len(helios_ctx["open_contradictions"]),
            "identity_warnings": helios_ctx["identity_warnings"],
        },
        "2_what_changed_over_time_and_which_source_wins": {
            "attribute": "plan_tier",
            "current_value": helios_plan["current_value"],
            "winner": next((f for f in helios_plan["facts"] if f["is_winner"]), None),
            "losers": [{"value": f["value"], "source": f["source"], "reliability": f["reliability"],
                        "eliminated_by": f["eliminated_by"]} for f in helios_plan["facts"] if not f["is_winner"]],
            "resolution_trace": helios_plan["resolution_trace"],
        },
        "3_account_policy_that_must_not_leak": {
            "helios_applicable_policies": [p["policy_entity_id"] for p in helios_ctx["applicable_policies"]],
            "nova_applicable_policies": [p["policy_entity_id"] for p in nova_ctx["applicable_policies"]],
            "note": "The Nova privacy policy is scoped to acct_nova_945 via related_entity_ids and never appears in Helios context.",
        },
        "4_duplicate_retries_or_idempotency_conflicts": {
            "idempotency_conflicts": [{"id": x["id"], "refs": x["refs"], "detail": x["detail"]}
                                      for x in conflicts if x["kind"] == "idempotency_conflict"],
            "note": "evt-1009 reused idem-1008 with a different body -> flagged conflict. evt-1008 self-describes as a retry of evt-1004 but carries a different idempotency_key, so it was processed as new (surfaced, not silently merged).",
        },
        "5_contacts_not_to_merge_without_review": [
            {"candidate_id": x["id"], "entities": x["refs"], "reason": x["detail"].get("reason") or x["kind"]}
            for x in conflicts if x["type"] == "identity_candidate"
        ],
    }
    _write("business_questions.json", business_questions)
    _write("ingest_results.json", ingest_results)


if __name__ == "__main__":
    main()
