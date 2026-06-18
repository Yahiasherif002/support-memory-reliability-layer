"""Clock abstraction.

Time is an injected dependency, never read ambiently. This keeps the whole
pipeline deterministic under test (staleness, ``as_of`` queries, ``received_at``)
and makes "now" explicit at every call site.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:  # pragma: no cover - protocol
        ...


class SystemClock:
    """Wall-clock UTC time. Used in production."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """Deterministic clock for tests and reproducible seeds."""

    def __init__(self, moment: datetime) -> None:
        self._moment = _ensure_aware(moment)

    def now(self) -> datetime:
        return self._moment

    def set(self, moment: datetime) -> None:
        self._moment = _ensure_aware(moment)

    def advance(self, **timedelta_kwargs) -> None:
        from datetime import timedelta

        self._moment = self._moment + timedelta(**timedelta_kwargs)


def ensure_utc(moment: datetime) -> datetime:
    """Normalize any datetime to timezone-aware UTC.

    Used at ingest so a client-supplied ``occurred_at`` (possibly naive) never
    causes a naive-vs-aware comparison inside the resolver.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


# Backwards-compatible internal alias.
_ensure_aware = ensure_utc
