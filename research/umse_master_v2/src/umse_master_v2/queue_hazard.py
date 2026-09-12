from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .contracts import EvidenceStatus, QueueSurvivalObservation


@dataclass(frozen=True)
class SurvivalPoint:
    time_seconds: float
    at_risk: int
    exits: int
    censored: int
    survival_probability: float
    cumulative_hazard: float


@dataclass(frozen=True)
class QueueLifetimeDiagnostics:
    status: EvidenceStatus
    sample_count: int
    observed_exits: int
    censored_count: int
    median_survival_seconds: float | None
    restricted_mean_survival_seconds: float | None
    curve: tuple[SurvivalPoint, ...]
    calibrated: bool
    reasons: tuple[str, ...]


def kaplan_meier_queue_lifetime(
    observations: Sequence[QueueSurvivalObservation],
    *,
    minimum_orders: int = 10,
) -> QueueLifetimeDiagnostics:
    """Kaplan-Meier style descriptive queue-lifetime estimator.

    Censored active orders are retained as censored. All-censored data is
    explicitly NOT_IDENTIFIABLE rather than being interpreted as infinite or
    maximum persistence.
    """

    if minimum_orders < 2:
        raise ValueError("minimum_orders must be >= 2")
    rows = tuple(observations)
    if len(rows) < minimum_orders:
        return QueueLifetimeDiagnostics(
            status=EvidenceStatus.INSUFFICIENT_DATA,
            sample_count=len(rows),
            observed_exits=sum(1 for r in rows if not r.censored),
            censored_count=sum(1 for r in rows if r.censored),
            median_survival_seconds=None,
            restricted_mean_survival_seconds=None,
            curve=(),
            calibrated=False,
            reasons=("MINIMUM_ORDER_COUNT_NOT_MET",),
        )

    exits_total = sum(1 for r in rows if not r.censored)
    censored_total = len(rows) - exits_total
    if exits_total == 0:
        return QueueLifetimeDiagnostics(
            status=EvidenceStatus.NOT_IDENTIFIABLE,
            sample_count=len(rows),
            observed_exits=0,
            censored_count=censored_total,
            median_survival_seconds=None,
            restricted_mean_survival_seconds=None,
            curve=(),
            calibrated=False,
            reasons=("ALL_ORDERS_CENSORED",),
        )

    by_time: dict[float, list[QueueSurvivalObservation]] = {}
    for row in rows:
        by_time.setdefault(float(row.lifetime_seconds), []).append(row)

    at_risk = len(rows)
    survival = 1.0
    cumulative_hazard = 0.0
    curve: list[SurvivalPoint] = []
    previous_time = 0.0
    restricted_mean = 0.0
    median_survival = None

    for time in sorted(by_time):
        # Survival between event times is constant, so integrate the previous
        # survival level over the interval for restricted mean survival time.
        restricted_mean += survival * max(0.0, time - previous_time)
        bucket = by_time[time]
        exits = sum(1 for r in bucket if not r.censored)
        censored = len(bucket) - exits
        if exits > at_risk:
            raise ValueError("exit count cannot exceed risk set")
        if exits > 0 and at_risk > 0:
            survival *= 1.0 - exits / at_risk
            cumulative_hazard += exits / at_risk
        curve.append(
            SurvivalPoint(
                time_seconds=time,
                at_risk=at_risk,
                exits=exits,
                censored=censored,
                survival_probability=max(0.0, min(1.0, survival)),
                cumulative_hazard=max(0.0, cumulative_hazard),
            )
        )
        if median_survival is None and survival <= 0.5:
            median_survival = time
        at_risk -= exits + censored
        previous_time = time

    reasons: list[str] = ["DESCRIPTIVE_SURVIVAL_NOT_PREDICTIVE_CALIBRATION"]
    if median_survival is None:
        reasons.append("MEDIAN_NOT_REACHED_WITHIN_OBSERVATION_WINDOW")

    return QueueLifetimeDiagnostics(
        status=EvidenceStatus.UNCALIBRATED,
        sample_count=len(rows),
        observed_exits=exits_total,
        censored_count=censored_total,
        median_survival_seconds=median_survival,
        restricted_mean_survival_seconds=restricted_mean,
        curve=tuple(curve),
        calibrated=False,
        reasons=tuple(reasons),
    )
