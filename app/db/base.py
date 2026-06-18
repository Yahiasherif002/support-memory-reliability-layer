"""Declarative base and shared column types.

``UTCDateTime`` is deliberately strict: SQLite stores naive datetimes, which is a
classic source of "naive vs aware" comparison bugs. Because the resolver and the
staleness checks do real datetime arithmetic, we normalize every datetime to
timezone-aware UTC on the way in *and* on the way out.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, TypeDecorator
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """A DateTime that always round-trips as timezone-aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
