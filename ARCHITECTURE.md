# Architecture

## Philosophy

The raw event log is the only source of truth. Facts and beliefs are *derived
projections* of it; everything except `raw_events` (and the idempotency registry)
can be dropped and rebuilt byte-for-byte. Uncertainty — contradictions, stale, low
reliability, ambiguous identity, duplicate/idempotency conflicts — is surfaced as
data, never silently flattened.

## The model (event → fact → entity → belief → context)

**Memory Event (Layer 1, `raw_events`)** — the assignment record verbatim:
`event_id, idempotency_key, occurred_at, source, actor, entity_type, entity_id,
related_entity_ids, reliability, text, payload`. `id` IS the `event_id`; `seq` is a
monotonic replay offset. Immutable; the one wall-clock stamp (`received_at`) is taken
once at ingest and every derived row reuses it.

**Fact (Layer 2, `facts`)** — a structured, immutable, bitemporal claim extracted
deterministically from `text` + `payload`, keyed by `source` and branched by
`entity_type`. Carries the source event's `reliability`, an `is_correction` flag,
`valid_from/valid_to` (valid time) and `recorded_at` (transaction time). Re-extraction
is idempotent via a content-addressed `dedupe_key` (incl. extractor version).

**Evidence (Layer 3, `fact_evidence`)** — edge from a fact to its source event and the
payload field it came from, so explanations point at *where* a value was read.

**Entity-scoped memory (Layer 5, `entities` + `entity_relations`)** — entities are
keyed directly by `(entity_type, entity_id)` from the event (`acct_helios_945`, …).
`related_entity_ids` become relation edges (account↔contact↔ticket↔policy) and power
policy isolation. Identity **ambiguity** (contacts sharing a phone/email) is recorded
as a candidate, never auto-merged.

**Belief (Layer 4, `beliefs`)** — the *derived* current value per `(entity, attribute)`.
A self-invalidating snapshot cache (`through_seq` + `recompute_after`); time-relative
flags (staleness/liveness) are computed at read, never stored. Reconstructable from facts.

**Context (Layer 6) & Explainability (Layer 7)** — both go through one
`BeliefResolutionEngine`, so they can't disagree. Context is compact, budgeted, and
policy-isolated; explain returns winner + every competing fact (+ the rule that
eliminated it) + evidence + the reasoning trace.

## Reliability-aware resolution

When values for one `(entity, attribute)` compete, the winner is chosen by:

1. **reliability** (high > medium > low) — the assignment's explicit trust signal;
2. **explicit correction / supersession** (a `correction`/`supersedes` event gets a bump);
3. **source authority** (contract > crm > system > agent_note > email > chat);
4. **recency** (`observed_at`);
5. **confidence**, then a deterministic id tiebreak.

A value is asserted/retracted by its *most recent* statement (recency-first), so a
recent retraction overrides higher authority. Confidence is the noisy-OR over the
winning value's corroborating facts. Two or more live values ⇒ a recorded
contradiction; the facts coexist. A winner older than its attribute's freshness window
⇒ `is_stale` (computed at read).

Worked examples on the data: Starter (crm/medium) and an old Starter note
(agent_note/low) lose to **Enterprise Support** (contract/high) — by reliability;
**42 → 48 seats** — the 48 email is `correction:true`, so it wins at equal reliability;
**WhatsApp → email-only** — evt-1013 carries `supersedes`, so email-only wins and the
WhatsApp conflict is surfaced.

## Policy isolation

Policies are first-class `policy` entities linked to an account via
`related_entity_ids`. Context for an account resolves `policy_rule` **only** from
related policy entities. Nova's DPA (`policy_nova_945_privacy`, scoped to
`acct_nova_945`) therefore appears in Nova's context and never in Helios's.

## Reliability & idempotency

- **Two-phase ingest.** Phase 1 atomically classifies idempotency and durably commits
  the raw event; phase 2 extracts/projects in a separate transaction. A processing
  failure can never lose the raw event.
- **Idempotency** keyed on `idempotency_key` via `INSERT … ON CONFLICT DO NOTHING`:
  same key + same body → the original logical result is returned, no new facts, replay
  counted (no duplicate raw rows); same key + different body → a recorded
  `idempotency_conflict`, stored as evidence, not processed.
- **Replay.** `ReplayEngine` rebuilds all derived state from `raw_events` in `seq`
  order; deterministic ids + event-sourced timestamps make it byte-identical
  (`tests/test_replay.py`), and it's checkpointed (`replay_metadata`) so it resumes.

## Context diff ("what changed since the last context build?")

Each build stores a cursor (`through_seq`) and a content hash of the belief set
(`context_builds`). The next build diffs the current belief set against the stored one
(added / removed / changed) and lists raw events since the cursor. Reconstructed
through the same engine, so the diff agrees with `/context` and `/explain`.

## Intentionally NOT built (with reasons)

- **LLM/NLP extraction** — deterministic rules keep it reproducible/testable/explainable; LLM is a documented drop-in (NEXT.md).
- **Async workers / message broker** — synchronous pipeline for a runnable local slice; outbox design in NEXT.md.
- **Automatic entity merge** — by design; ambiguous contacts are surfaced for human review.
- **AuthN/Z, multi-tenancy, rate limiting, metrics/tracing** — out of scope for the sample.
- **PII redaction/retention** — flagged; it conflicts with immutability and needs crypto-shredding (NEXT.md).
- **Phone/name fuzzy matching** — identity ambiguity uses exact normalized phone/email; fuzzy matching is future work.
