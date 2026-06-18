"""Belief-resolution precedence — reliability-first, with explicit corrections.

Two orderings:

* **winner_key** (choosing between competing values): reliability → source
  authority → recency → confidence → deterministic tiebreak. A ``correction``
  fact (an event that explicitly corrects/supersedes a prior value) gets a rank
  bump so a deliberate fix beats an older high-reliability value.
* **retraction_key** (is one value currently asserted or retracted): recency-first,
  so a recent retraction is effective regardless of source authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.policies.reliability import rank
from app.policies.source_priority import authority


@dataclass(frozen=True)
class ResolutionPolicy:
    name: str = "reliability-precedence-v1"
    corroboration: bool = True

    def winner_key(self, fact) -> tuple:
        correction_bonus = 1 if getattr(fact, "is_correction", False) else 0
        return (rank(fact.reliability) + correction_bonus, authority(fact.source), fact.observed_at, fact.confidence)

    def retraction_key(self, fact) -> tuple:
        return (fact.observed_at, rank(fact.reliability), authority(fact.source))


DEFAULT_POLICY = ResolutionPolicy()
