# Support Memory Reliability Layer

A small, local, event-sourced **memory service** for an AI support assistant
(stakeholder: Lina Farouk, Aster Support). It ingests the assignment's Memory
Events, preserves them immutably, extracts evidence-linked facts, scopes memory to
the right account/contact/ticket/policy, derives current beliefs while surfacing
contradictions / stale / ambiguous / duplicate signals, and returns compact context
for a rep — with an explain view for every belief.

> **Dataset:** `data/seed_events.json` is the assignment's exact 20-event dataset,
> ingested **unmodified**. Ingestion is schema-driven, so replacing that file with
> any conforming Memory Event list runs with zero code changes.

## Quickstart (uses [uv](https://docs.astral.sh/uv/))

```bash
uv sync                                        # venv + deps
uv run python scripts/load_seed.py             # ingest the 20 events into ./support_memory.db
uv run uvicorn app.main:app --reload           # http://127.0.0.1:8000/docs
uv run pytest -q                               # 26 tests
uv run python scripts/generate_samples.py      # regenerate sample_outputs/
uv run python scripts/rebuild_projections.py   # rebuild ALL derived state from the raw log
```

## The Memory Event (assignment schema, accepted verbatim)

`event_id · idempotency_key · occurred_at · source(crm|contract|chat|email|agent_note|system)
· actor · entity_type(account|contact|ticket|policy) · entity_id · related_entity_ids[]
· reliability(high|medium|low) · text · payload`

There is **no `event_type`** — extraction reads `text` + `payload`, keyed by `source`.

## Architecture (layers)

```
ingest → [1] raw_events (immutable, append-only; stores actor/reliability/related/text verbatim)
       → [2] extraction (deterministic rules over text+payload, keyed by source)
       → [3] evidence graph (fact → source event + payload locator)
       → [5] entity-scoped memory: entities keyed by (entity_type, entity_id); related_entity_ids → relations
       → [4] belief resolution: reliability → source authority → recency → confidence (+correction); retraction
read   → [6] context (compact, budgeted, evidence-linked; policy-isolated) + context/diff
       → [7] explainability (why a belief holds; + per-event lineage)
```

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/events:ingest` (+ `:ingest-batch`) | Ingest a Memory Event. 200 always; body's `dedup_status` classifies it. Retry → same logical result. |
| GET | `/v1/entities/{id}/context` | Compact, evidence-linked context (policy-isolated). |
| GET | `/v1/entities/{id}/context/diff` | What changed since the last context build. |
| GET | `/v1/entities/{id}/explain?attribute=` | Why a belief holds: winner + losers + evidence + trace. |
| GET | `/v1/events/{event_id}/explain` | Event lineage: idempotency + identity decision + facts produced. |
| GET | `/v1/conflicts` · PATCH `/v1/conflicts/{id}` | Unified contradictions + identity candidates; non-destructive status. |

## Business questions (answers in `sample_outputs/`)

1. **What should a rep know before calling Helios?** → `helios_context.json`: plan **Enterprise Support** (high), P1 SLA 2h, region Cairo; Mona now **email-only except P1**; open contradictions + a do-not-merge warning.
2. **What changed over time / which source wins?** → `helios_explain_plan.json`: Starter (crm/medium) and an old Starter note (agent_note/low) lose to **Enterprise Support (contract/high)** — eliminated *by reliability*.
3. **Which policy must not leak?** → `business_questions.json`: Nova's privacy policy is scoped to `acct_nova_945`; Helios context `applicable_policies == []`.
4. **Duplicate retries / idempotency conflicts?** → `conflicts.json`: `evt-1009` reused `idem-1008` with a different body → flagged conflict.
5. **Which contacts must not be merged?** → M. Salem and Omar share a phone → identity candidate, surfaced not merged.

## Design decisions & tradeoffs

- **Deterministic extraction** (rules over text+payload), not an LLM: reproducible, testable, and fully explainable. The registry is keyed by `source` so an LLM extractor can drop in behind the same interface.
- **Reliability-first resolution**, then source authority, recency, confidence, with a bump for explicit corrections/supersession; a recent retraction overrides authority. Conflicting facts **coexist** and are surfaced, never flattened.
- **Beliefs are derived**, never authored — the whole projection rebuilds from `raw_events` (deterministic ids + timestamps from the event), proven by a rebuild-from-empty test.
- **Idempotency** keyed on `idempotency_key`: same key+body → same logical result, no duplicate facts; same key+different body → recorded conflict.
- **SQLite + FastAPI + SQLAlchemy 2.0 + Pydantic v2**, easy to run locally.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full model, reliability assumptions, and
what was intentionally not built. Build log: [DAILY_UPDATE.md](DAILY_UPDATE.md) ·
next steps: [NEXT.md](NEXT.md) · AI workflow: [AI_USAGE.md](AI_USAGE.md).
