"""Test helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.hashing import sha256_hex
from app.core.ids import new_id
from app.db.models import Fact
from app.domain.enums import Polarity, Reliability, Source


def aware(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def make_fact(
    *,
    entity_id: str = "e1",
    attribute: str = "plan_tier",
    value: Any = "Starter",
    source: Source = Source.CRM,
    reliability: Reliability = Reliability.MEDIUM,
    observed_at: datetime,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    confidence: float = 0.6,
    polarity: Polarity = Polarity.ASSERT,
    is_correction: bool = False,
    fact_id: str | None = None,
    dedupe_key: str | None = None,
    source_event_id: str = "evt",
) -> Fact:
    fid = fact_id or new_id("fact")
    return Fact(
        id=fid, entity_id=entity_id, attribute=attribute, value=value, value_hash=sha256_hex(value),
        valid_from=valid_from or observed_at, valid_to=valid_to, observed_at=observed_at, recorded_at=observed_at,
        confidence=confidence, source=str(source), reliability=str(reliability), polarity=str(polarity),
        is_correction=is_correction, extractor_name="test", extractor_version="1",
        source_event_id=source_event_id, dedupe_key=dedupe_key or fid)
