# NEXT — if this became production

Ranked by impact.

1. **Async, durable pipeline.** Today ingestion is synchronous (raw event committed
   in its own transaction, then processing in a second). For scale, emit to an outbox
   and process via workers/CDC so each projection is independently replayable and a
   slow extractor can't block ingest.

2. **Postgres profile.** Swap SQLite for Postgres: JSONB + GIN indexes, `tstzrange`
   exclusion constraints to enforce temporal non-overlap in the DB, and a real
   `INSERT … ON CONFLICT` upsert under genuine write concurrency (the idempotency
   design already assumes this). Repositories isolate the dialect.

3. **LLM extractor for free text.** The registry is keyed by `source`; add an
   LLM-backed extractor for `chat`/`email` that emits the same `ExtractedFact` shape
   (attribute, value, confidence, locator). Keep the deterministic rules as the
   verifiable floor and to ground/verify the LLM's output.

4. **Identity resolution workflow.** Promote identity candidates into a review queue
   with confirm-same / confirm-distinct actions, an audit trail, and a merged-view that
   never destroys the underlying entities.

5. **Richer reliability model.** Per-source calibration, decay of authority over time,
   and confidence that blends corroboration with disagreement (currently noisy-OR over
   the winning value only).

6. **Operational hardening.** AuthN/Z, rate limiting, multi-tenancy, PII
   redaction/retention compatible with immutability (crypto-shredding), metrics
   (contradiction rate, stale ratio, extraction coverage), and tracing.

7. **Context quality.** Vector/semantic retrieval to complement the structured +
   recency ranking; per-attribute freshness tuning from real data; and a richer
   context diff (digest summaries, not just per-attribute changes).
