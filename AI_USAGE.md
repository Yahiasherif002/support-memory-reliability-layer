# AI Usage

I used an AI coding assistant the way a senior engineer uses a strong pair: I owned
the architecture, the data contract, and the definition of done, and I verified every
output against the assignment's data and an automated test suite before trusting it.
AI accelerated the typing and the boilerplate; the engineering judgment, the
acceptance criteria, the checks, and the corrections were mine. This file documents
that workflow, as the brief asks.

## My method (how I directed the work)

- **Decomposed before coding.** I fixed the layering up front — immutable event log →
  fact extraction → evidence graph → entity-scoped memory → reliability-aware belief
  resolution → context/explainability — and handed the model that structure plus the
  five business questions as the spec, rather than a vague "build a memory service."
- **Gave precise context at each step.** The exact Memory Event schema, the
  reliability/idempotency requirements, and concrete, testable acceptance criteria —
  e.g. "Nova's privacy policy must never appear in Helios context," "42 affected seats
  must be corrected to 48," "a retry with the same idempotency key returns the same
  logical result and creates no new facts."
- **Worked in small, verifiable units** and kept a green test suite as the contract,
  so any regression surfaced immediately instead of hiding in a large diff.

## How I verified outputs (rather than trusting them)

- **Ran everything on the real 20-event dataset** (`scripts/load_seed.py`) and pinned
  the outcomes in tests (`tests/test_seed_dataset.py`, `tests/test_business_questions.py`).
  Before changing anything, I *proved* a problem existed by feeding the brief's
  `evt-1001` through the ingest model and watching it fail validation.
- **Wrote 26 tests** as my safety net against plausible-but-wrong output: resolution
  precedence, idempotency replay + conflict, rebuild-from-raw determinism, an
  advanced-clock replay (proving beliefs don't drift with wall-clock time), policy
  isolation, identity ambiguity, context diff, and evidence-linked explainability.

## Specific errors I caught and corrected

- **Schema drift.** An early iteration quietly invented its own event shape (a
  non-existent `event_type`, the wrong source/entity vocabulary, and it ignored
  `reliability`, `actor`, and `related_entity_ids`). I ran a release-blocking
  conformance review, demonstrated that the dataset would not ingest as-is, and
  re-targeted ingestion to the assignment schema exactly.
- **Over-eager extraction.** The model mapped an account-level `payload.preference`
  ("finance dashboard uptime") — and a passing mention of "phone escalation" — onto a
  *contact* channel. I separated account-preference from contact-preference and
  constrained channel inference to contact entities only.
- **Wrong identity signal.** It first keyed identity ambiguity on a shared email; the
  dataset's real signal is a shared **phone** (M. Salem / Omar, plausibly different
  people on different accounts). I corrected the detector and the corresponding test.
- **Semantics over surface.** I kept "Enterprise Support" verbatim instead of
  lower-casing it, and modeled explicit `correction`/`supersedes` so 48 beats 42 and
  the email-only rule supersedes WhatsApp — both with the prior value still visible as
  a surfaced contradiction, never silently overwritten.

## Tradeoffs I decided, and why

- **Deterministic rule-based extraction over an LLM extractor:** reproducible,
  testable, and fully explainable for a reliability layer; the extractor registry is
  keyed by `source`, so an LLM extractor can drop in behind the same interface later.
- **Reliability-first belief resolution** (reliability → correction → source authority
  → recency → confidence), with conflicting/stale facts surfaced rather than flattened.
- **SQLite + a synchronous pipeline** for a slice that runs locally in one command; I
  documented the async/outbox and Postgres path in `NEXT.md` rather than half-building it.

## Disclosure & tooling

Per the assignment, I'm disclosing AI use openly: I used a frontier AI coding model as
a pair-programmer, with `uv` and `pytest` to execute and verify locally. This document
is my written account of that usage; the commit history, the tests, and the generated
`sample_outputs/` are the evidence trail behind it.
