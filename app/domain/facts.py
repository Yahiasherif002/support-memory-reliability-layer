"""Fact-related domain types.

``ExtractedFact`` is an extractor's output. ``confidence=None`` means "derive it
from the event's reliability"; an extractor may pin a value explicitly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import Polarity


class ExtractedFact(BaseModel):
    attribute: str
    value: Any
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: float | None = None
    polarity: Polarity = Polarity.ASSERT
    is_correction: bool = False
    locator: dict[str, Any] = Field(default_factory=dict)
