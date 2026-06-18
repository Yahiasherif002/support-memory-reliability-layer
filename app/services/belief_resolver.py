"""Layer 4 — reliability-aware belief resolution (the single source of truth).

``resolve(facts, as_of)`` is pure (reads no wall-clock), so replay is deterministic.
Winner selection is **reliability-first**, then source authority, recency,
confidence, with a bump for explicit corrections; a recent retraction removes a
value regardless of authority. Confidence is the noisy-OR over the winning value's
corroborating facts. ``is_stale``/liveness are computed at ``as_of`` (never stored);
``recompute_after`` lets the snapshot self-invalidate.
"""

from __future__ import annotations

from datetime import datetime
from itertools import groupby

from app.core.clock import Clock
from app.core.hashing import sha256_hex
from app.core.ids import deterministic_id
from app.db.models import Contradiction, Fact
from app.db.repositories import ContradictionRepository, EntityRepository, FactRepository
from app.domain.beliefs import CandidateVerdict, ContradictionFinding, Resolution, ResolutionStep
from app.domain.enums import ContradictionKind, Polarity
from app.policies import freshness
from app.policies.reliability import rank
from app.policies.resolution import DEFAULT_POLICY, ResolutionPolicy
from app.policies.source_priority import authority
from app.services.snapshot_manager import SnapshotManager


def _ordered(facts: list[Fact], keyfn) -> list[Fact]:
    by_id = sorted(facts, key=lambda f: f.id)
    return sorted(by_id, key=keyfn, reverse=True)


def _noisy_or(confidences: list[float]) -> float:
    product = 1.0
    for c in confidences:
        product *= 1.0 - max(0.0, min(1.0, c))
    return round(1.0 - product, 6)


def _deciding_rule(winner: Fact, runner: Fact) -> ResolutionStep:
    if rank(winner.reliability) != rank(runner.reliability):
        detail = f"reliability {winner.reliability} outranks {runner.reliability}"
        rule = "reliability"
    elif getattr(winner, "is_correction", False) != getattr(runner, "is_correction", False):
        detail = "an explicit correction supersedes the prior value"
        rule = "correction"
    elif authority(winner.source) != authority(runner.source):
        detail = f"{winner.source} outranks {runner.source} by source authority"
        rule = "source_authority"
    elif winner.observed_at != runner.observed_at:
        detail = f"observed_at {winner.observed_at.isoformat()} is newer"
        rule = "recency"
    elif winner.confidence != runner.confidence:
        detail = f"confidence {winner.confidence} exceeds {runner.confidence}"
        rule = "confidence"
    else:
        detail = f"deterministic tiebreak: {winner.id} precedes {runner.id}"
        rule = "tiebreak"
    return ResolutionStep(rule=rule, detail=detail, winner_fact_id=winner.id, loser_fact_id=runner.id)


def _next_boundary(facts: list[Fact], as_of: datetime, winner: Fact | None, attribute: str) -> datetime | None:
    boundaries: list[datetime] = []
    for f in facts:
        if f.valid_from > as_of:
            boundaries.append(f.valid_from)
        if f.valid_to is not None and f.valid_to > as_of:
            boundaries.append(f.valid_to)
    if winner is not None:
        flip = winner.observed_at + freshness.ttl_for(attribute)
        if flip > as_of:
            boundaries.append(flip)
    return min(boundaries) if boundaries else None


def resolve(entity_id, attribute, facts, as_of, policy: ResolutionPolicy = DEFAULT_POLICY) -> Resolution:
    live = [f for f in facts if f.valid_from <= as_of and (f.valid_to is None or as_of < f.valid_to)]
    considered = [f.id for f in live]
    trace = [ResolutionStep(rule="scope", detail=f"{len(live)} of {len(facts)} fact(s) valid at as_of={as_of.isoformat()}")]

    if not live:
        trace.append(ResolutionStep(rule="no_live_facts", detail="no facts valid at as_of"))
        return Resolution(entity_id=entity_id, attribute=attribute, as_of=as_of, policy=policy.name,
                          considered_fact_ids=considered, trace=trace,
                          recompute_after=_next_boundary(facts, as_of, None, attribute))

    groups: dict[str, list[Fact]] = {}
    for f in live:
        groups.setdefault(f.value_hash, []).append(f)

    active_reps: dict[str, Fact] = {}
    retracted: list[Fact] = []
    for vh, group in groups.items():
        top = _ordered(group, policy.retraction_key)[0]
        if top.polarity == Polarity.ASSERT:
            asserts = [f for f in group if f.polarity == Polarity.ASSERT]
            active_reps[vh] = _ordered(asserts, policy.winner_key)[0]
        else:
            retracted.append(top)
    for rt in retracted:
        trace.append(ResolutionStep(rule="retraction", detail=f"value {rt.value!r} retracted by {rt.id} ({rt.source})", winner_fact_id=rt.id))

    if not active_reps:
        trace.append(ResolutionStep(rule="all_retracted", detail="every candidate value is retracted"))
        return Resolution(entity_id=entity_id, attribute=attribute, as_of=as_of, policy=policy.name,
                          considered_fact_ids=considered,
                          verdicts=[CandidateVerdict(fact_id=t.id, value=t.value, won=False, eliminated_by="retraction") for t in retracted],
                          trace=trace, recompute_after=_next_boundary(facts, as_of, None, attribute))

    ordered = _ordered(list(active_reps.values()), policy.winner_key)
    winner = ordered[0]
    trace.append(_deciding_rule(winner, ordered[1]) if len(ordered) > 1
                 else ResolutionStep(rule="uncontested", detail=f"single asserted value, fact {winner.id}", winner_fact_id=winner.id))

    is_contradicted = len(ordered) > 1
    findings = []
    if is_contradicted:
        for other in ordered[1:]:
            findings.append(ContradictionFinding(
                kind=ContradictionKind.BELIEF_VALUE_CONFLICT, entity_id=entity_id, attribute=attribute,
                fact_id_a=winner.id, fact_id_b=other.id,
                detail={"winner_value": winner.value, "other_value": other.value,
                        "winner_reliability": winner.reliability, "other_reliability": other.reliability,
                        "winner_source": winner.source, "other_source": other.source}))
        trace.append(ResolutionStep(rule="contradiction", detail=f"{len(ordered)} asserted values coexist; winner is current belief, conflict recorded, facts kept"))

    supporters = [f for f in groups[winner.value_hash] if f.polarity == Polarity.ASSERT]
    confidence = _noisy_or([f.confidence for f in supporters]) if policy.corroboration else winner.confidence
    basis = f"noisy-OR over {len(supporters)} corroborating fact(s)" if policy.corroboration else "winner confidence"
    trace.append(ResolutionStep(rule="confidence", detail=f"belief confidence {confidence} ({basis})", winner_fact_id=winner.id))

    is_stale = freshness.is_stale(attribute, winner.observed_at, as_of)
    if is_stale:
        trace.append(ResolutionStep(rule="staleness", detail=f"winning fact observed {winner.observed_at.isoformat()} is older than the freshness window", winner_fact_id=winner.id))

    verdicts = [CandidateVerdict(fact_id=r.id, value=r.value, won=(r.id == winner.id),
                                 eliminated_by=None if r.id == winner.id else _deciding_rule(winner, r).rule) for r in ordered]
    verdicts += [CandidateVerdict(fact_id=t.id, value=t.value, won=False, eliminated_by="retraction") for t in retracted]

    return Resolution(entity_id=entity_id, attribute=attribute, as_of=as_of, current_value=winner.value,
                      winning_fact_id=winner.id, winner_observed_at=winner.observed_at, policy=policy.name,
                      is_contradicted=is_contradicted, is_stale=is_stale, confidence=confidence, confidence_basis=basis,
                      recompute_after=_next_boundary(facts, as_of, None if is_stale else winner, attribute),
                      considered_fact_ids=considered, contributing_fact_ids=[f.id for f in supporters],
                      verdicts=verdicts, trace=trace, findings=findings)


# --- read engine (shared by context + explain) --------------------------
class BeliefResolutionEngine:
    def __init__(self, facts: FactRepository, clock: Clock, policy: ResolutionPolicy = DEFAULT_POLICY) -> None:
        self.facts = facts
        self.clock = clock
        self.policy = policy

    def reconstruct(self, entity_id: str, attribute: str, as_of: datetime | None = None) -> Resolution:
        at = as_of or self.clock.now()
        return resolve(entity_id, attribute, self.facts.list_for_entity_attribute(entity_id, attribute), at, self.policy)

    def reconstruct_entity(self, entity_id: str, as_of: datetime | None = None) -> dict[str, Resolution]:
        at = as_of or self.clock.now()
        facts = self.facts.list_for_entity(entity_id)
        return {attr: resolve(entity_id, attr, list(group), at, self.policy)
                for attr, group in groupby(facts, key=lambda f: f.attribute)}


# --- projection ----------------------------------------------------------
def contradiction_dedupe_key(finding: ContradictionFinding) -> str:
    lo, hi = sorted([finding.fact_id_a, finding.fact_id_b])
    return sha256_hex([str(finding.kind), finding.entity_id, finding.attribute, lo, hi])


class ProjectionService:
    def __init__(self, *, facts: FactRepository, snapshots: SnapshotManager,
                 contradictions: ContradictionRepository, entities: EntityRepository,
                 clock: Clock, policy: ResolutionPolicy = DEFAULT_POLICY) -> None:
        self.facts = facts
        self.snapshots = snapshots
        self.contradictions = contradictions
        self.entities = entities
        self.clock = clock
        self.policy = policy

    def project_attribute(self, entity_id: str, attribute: str):
        now = self.clock.now()
        facts = self.facts.list_for_entity_attribute(entity_id, attribute)
        res = resolve(entity_id, attribute, facts, now, self.policy)
        through_seq = self.facts.high_water_seq(entity_id, attribute)
        belief = self.snapshots.write(res, through_seq=through_seq, computed_at=now)

        current_keys: set[str] = set()
        ids: list[str] = []
        for finding in res.findings:
            dk = contradiction_dedupe_key(finding)
            current_keys.add(dk)
            row, _ = self.contradictions.add_idempotent(Contradiction(
                id=deterministic_id("con", dk), entity_id=finding.entity_id, attribute=finding.attribute,
                kind=str(finding.kind), fact_id_a=finding.fact_id_a, fact_id_b=finding.fact_id_b,
                detail=finding.detail, status="open", detected_at=now, updated_at=now, dedupe_key=dk))
            ids.append(row.id)
        for existing in self.contradictions.list_live_for_attribute(entity_id, attribute):
            if existing.dedupe_key not in current_keys:
                self.contradictions.auto_close(existing, now, "values no longer jointly valid at resolution time")
        return belief, ids

    def project_entity(self, entity_id: str) -> list[str]:
        ids: list[str] = []
        for attribute in self.facts.distinct_attributes(entity_id):
            _b, cids = self.project_attribute(entity_id, attribute)
            ids.extend(cids)
        return ids
