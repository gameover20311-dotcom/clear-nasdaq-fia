from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import random
from typing import Iterable

from .contracts import EvidenceStatus
from .information_velocity import TimedShock


@dataclass(frozen=True)
class LeadLagEvidence:
    status: EvidenceStatus
    source_node: str
    target_node: str
    observed_score: float | None
    null_mean: float | None
    p_value: float | None
    permutations: int
    source_events: int
    target_events: int
    alpha: float
    significant_screen: bool
    calibrated: bool = False
    promotion_eligible: bool = False
    reasons: tuple[str, ...] = ()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _match_score(source_times: list[datetime], target_times: list[datetime], max_lag_seconds: float) -> float:
    """Density-aware timing score before null calibration.

    Each source uses at most one subsequent target and each target is consumed at
    most once. Fast responses score closer to 1; unmatched sources score zero.
    Simultaneous observations score zero because timestamp resolution does not
    establish direction.
    """

    if not source_times:
        return 0.0
    targets = sorted(target_times)
    used: set[int] = set()
    total = 0.0
    for source in sorted(source_times):
        chosen = None
        for j, target in enumerate(targets):
            if j in used:
                continue
            lag = (target - source).total_seconds()
            if lag <= 0:
                continue
            if lag > max_lag_seconds:
                break
            chosen = (j, lag)
            break
        if chosen is None:
            continue
        j, lag = chosen
        used.add(j)
        total += math.exp(-lag / max_lag_seconds)
    return total / len(source_times)


def circular_shift_leadlag_evidence(
    shocks: Iterable[TimedShock],
    decision_time_utc: datetime,
    *,
    source_node: str,
    target_node: str,
    max_lag_seconds: float,
    permutations: int = 999,
    alpha: float = 0.01,
    seed: int = 20260912,
    minimum_events_per_node: int = 20,
) -> LeadLagEvidence:
    """Screen apparent lead-lag against a circular-shift timing null.

    The null preserves the target event count and cyclic inter-arrival structure
    while destroying alignment to source events. It is a screening null, not a
    proof of economic causality; exchange/feed latency still requires explicit
    measurement before any directional causal claim.
    """

    if source_node == target_node:
        raise ValueError("source_node and target_node must differ")
    if max_lag_seconds <= 0 or not math.isfinite(max_lag_seconds):
        raise ValueError("max_lag_seconds must be finite and > 0")
    if permutations < 1:
        raise ValueError("permutations must be >= 1")
    if not (0 < alpha < 1):
        raise ValueError("alpha must be in (0,1)")
    if 1.0 / (permutations + 1) > alpha:
        raise ValueError("permutation count cannot resolve requested alpha")
    if minimum_events_per_node < 3:
        raise ValueError("minimum_events_per_node must be >= 3")

    decision = _utc(decision_time_utc)
    eligible = [s for s in shocks if s.eligible_at(decision)]
    source = [s.event_time_utc for s in eligible if s.node == source_node]
    target = [s.event_time_utc for s in eligible if s.node == target_node]

    if len(source) < minimum_events_per_node or len(target) < minimum_events_per_node:
        return LeadLagEvidence(
            status=EvidenceStatus.INSUFFICIENT_DATA,
            source_node=source_node,
            target_node=target_node,
            observed_score=None,
            null_mean=None,
            p_value=None,
            permutations=0,
            source_events=len(source),
            target_events=len(target),
            alpha=alpha,
            significant_screen=False,
            reasons=("MINIMUM_EVENTS_PER_NODE_NOT_MET",),
        )

    start = min(min(source), min(target))
    end = max(max(source), max(target))
    span = (end - start).total_seconds()
    if span <= max_lag_seconds * 2:
        return LeadLagEvidence(
            status=EvidenceStatus.NOT_IDENTIFIABLE,
            source_node=source_node,
            target_node=target_node,
            observed_score=None,
            null_mean=None,
            p_value=None,
            permutations=0,
            source_events=len(source),
            target_events=len(target),
            alpha=alpha,
            significant_screen=False,
            reasons=("OBSERVATION_SPAN_TOO_SHORT_FOR_SHIFT_NULL",),
        )

    observed = _match_score(source, target, max_lag_seconds)
    target_offsets = [(t - start).total_seconds() for t in target]
    rng = random.Random(seed)
    nulls: list[float] = []
    for _ in range(permutations):
        # Avoid a near-zero shift, which would copy the observed alignment into
        # the null. The offset is otherwise uniform over the observation circle.
        shift = rng.uniform(max_lag_seconds, span - max_lag_seconds)
        shifted = [start + timedelta(seconds=((x + shift) % span)) for x in target_offsets]
        nulls.append(_match_score(source, shifted, max_lag_seconds))

    at_least = sum(1 for value in nulls if value >= observed - 1e-15)
    p_value = (1.0 + at_least) / (permutations + 1.0)
    null_mean = sum(nulls) / len(nulls)
    significant = p_value <= alpha
    return LeadLagEvidence(
        status=EvidenceStatus.UNCALIBRATED,
        source_node=source_node,
        target_node=target_node,
        observed_score=observed,
        null_mean=null_mean,
        p_value=p_value,
        permutations=permutations,
        source_events=len(source),
        target_events=len(target),
        alpha=alpha,
        significant_screen=significant,
        calibrated=False,
        promotion_eligible=False,
        reasons=(
            "SIGNIFICANCE_IS_SCREEN_ONLY",
            "DIRECTIONAL_CAUSALITY_REQUIRES_MEASURED_LATENCY_AND_CONFOUND_CONTROL",
        ),
    )
