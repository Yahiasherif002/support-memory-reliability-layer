"""Reliability policy — the assignment's per-event trust signal (high/medium/low).

``rank`` drives belief resolution (a more reliable fact wins); ``weight`` seeds a
fact's numeric confidence before corroboration.
"""

from __future__ import annotations

from app.domain.enums import Reliability

RELIABILITY_RANK: dict[str, int] = {Reliability.HIGH: 3, Reliability.MEDIUM: 2, Reliability.LOW: 1}
RELIABILITY_WEIGHT: dict[str, float] = {Reliability.HIGH: 0.9, Reliability.MEDIUM: 0.6, Reliability.LOW: 0.3}


def rank(reliability: str) -> int:
    return RELIABILITY_RANK.get(reliability, 0)


def weight(reliability: str) -> float:
    return RELIABILITY_WEIGHT.get(reliability, 0.3)
