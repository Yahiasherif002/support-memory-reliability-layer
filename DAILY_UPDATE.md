# Daily Update

## 2026-06-18 — Conformance to the assignment schema

**Branch:** `conformance/assignment-schema`
**Commit range:** initial commit (project root) on this branch.

### What shipped
A local, event-sourced support-memory service that ingests the assignment's exact
20-event dataset **unmodified** and answers all five business questions.

- **Data contract = the brief.** `MemoryEvent` accepts
  `event_id/idempotency_key/occurred_at/source/actor/entity_type/entity_id/related_entity_ids/reliability/text/payload`.
  No `event_type`. Sources `crm|contract|chat|email|agent_note|system`; entity types
  `account|contact|ticket|policy`. `actor`, `reliability`, `related_entity_ids` persisted.
- **Extraction** from `text` + `payload`, keyed by `source`, entity-type aware
  (plans, support tiers, SLA targets, seats incl. the 42→48 correction, contact/account
  preferences, regions/segments, ticket status, policies, contact email/phone).
- **Reliability-aware resolution**: reliability → correction → source authority →
  recency → confidence; recency-first retraction; noisy-OR corroboration.
- **Policy isolation** via `related_entity_ids` (Nova's policy never reaches Helios).
- **Identity ambiguity** (shared phone → M. Salem / Omar) surfaced, never merged.
- **Idempotency** (replay → same logical result; key-collision → conflict),
  **deterministic replay/rebuild**, **context diff**, and **evidence-linked explain**
  (belief + per-event lineage).

### Files changed (high level)
- `app/domain/` — `enums`, `events` (MemoryEvent), `facts`, `entities`, `context`, `explain`.
- `app/db/` — `models.py` (raw_events brief fields, entities-by-id, `entity_relations`,
  `context_builds`, Fact `reliability`/`is_correction`); repositories.
- `app/policies/` — `reliability`, `source_priority`, `resolution`, `attributes`, `freshness`, `importance`.
- `app/services/` — `extraction/rules.py`, `belief_resolver`, `identity_service`,
  `ingest_service`, `context_builder`, `context_diff`, `explainability`, `replay_engine`, `snapshot_manager`.
- `app/api/` — `routes/ingest|context|explain|conflicts`, `deps`, `main`.
- `data/seed_events.json` (the 20 events), `scripts/load_seed.py`, `scripts/generate_samples.py`,
  `scripts/rebuild_projections.py`, `sample_outputs/*`, `tests/*`, all docs.

### Tests / results
- `uv run pytest` → **26 passed** (resolution precedence, seed ingestion, 5 business
  questions, idempotency replay + conflict, rebuild-from-empty determinism,
  advanced-clock replay, context diff, explainability).
- `uv run python scripts/load_seed.py` → 20 events, 9 entities, 24 facts, 4 open
  contradictions (1 idempotency), 1 identity candidate.
- `sample_outputs/` regenerated deterministically.

### Blockers
None. (The prompt's pasted dataset was initially truncated; the full 20 events were
provided and are now committed verbatim as `data/seed_events.json`.)

### Next step
Async/outbox processing + Postgres profile, then an LLM extractor for free text behind
the existing source-keyed registry (see NEXT.md).
