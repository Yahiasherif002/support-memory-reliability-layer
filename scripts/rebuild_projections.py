"""Rebuild ALL derived state from the immutable raw log.

Truncates entities, facts, evidence, beliefs, and value-conflicts, then replays
``raw_events`` in ``seq`` order through the deterministic pipeline. Because derived
ids and timestamps come from the log, the result is byte-identical — the proof that
the system is event-sourced. The rebuild is checkpointed and resumable.

Run with:  uv run python scripts/rebuild_projections.py
"""

from __future__ import annotations

import sys

from app.core.clock import SystemClock
from app.core.config import get_settings
from app.db.session import build_engine, make_session_factory
from app.services.replay_engine import ReplayEngine


def main(resume: bool = False) -> None:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    session = make_session_factory(engine)()

    summary = ReplayEngine(session, SystemClock()).rebuild_all(resume=resume)
    session.close()

    print(
        f"Rebuilt all derived state from {summary['events_processed']} raw event(s) "
        f"(through seq {summary['through_seq']}, run {summary['run_id']})."
    )


if __name__ == "__main__":
    main(resume="--resume" in sys.argv)
