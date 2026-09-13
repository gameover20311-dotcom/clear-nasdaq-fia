from __future__ import annotations

from dataclasses import dataclass
import math
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
    restricted_mean_tau_seconds: float | None
    follow_up_reaches_tau: bool
    curve: tuple[SurvivalPoint, ...]
    calibrated: bool
    reasons: tuple[str, ...]


def kaplan_meier_queue_lifetime(
    observations: Sequence[QueueSurvivalObservation],
    *,
    minimum_orders: int = 10,
    tau_seconds: float | None = None,
) -> QueueLifetimeDiagnostics:
    """Kaplan-Meier style descriptive queue-lifetime estimator.

    Censored active orders are retained as censored. All-censored data is
    explicitly NOT_IDENTIFIABLE rather than being interpreted as infinite or
    maximum persistence.

    RESTRICTED MEAN SURVIVAL TIME REQUIRES AN EXPLICIT, OBSERVED TAU.
    RMST is only returned when `tau_seconds` is supplied and the observation
    window actually reaches that horizon.  We do not extrapolate a constant
    survival tail beyond the last observed follow-up and we do not publish the
    data-dependent integral to "whatever the sample happened to reach" as RMST.
    """
    if tau_seconds is not None and (not math.isfinite(float(tau_seconds)) or tau_seconds <= 0):
        raise ValueError("tau_seconds must be finite and > 0")

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
            restricted_mean_tau_seconds=tau_seconds,
            follow_up_reaches_tau=False,
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
            restricted_mean_tau_seconds=tau_seconds,
            follow_up_reaches_tau=False,
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

    horizon = float(tau_seconds) if tau_seconds is not None else None
    for time in sorted(by_time):
        # Survival between event times is constant. When tau is supplied, the
        # integral stops at tau.  We still build the descriptive KM curve over
        # the full observed sample, but no unsupported tail is added later.
        upper = time if horizon is None else min(time, horizon)
        restricted_mean += survival * max(0.0, upper - previous_time)
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
        previous_time = time if horizon is None else min(time, horizon)

    max_observed = max(by_time) if by_time else 0.0
    reaches_tau = horizon is not None and max_observed >= horizon

    reasons: list[str] = ["DESCRIPTIVE_SURVIVAL_NOT_PREDICTIVE_CALIBRATION"]
    if median_survival is None:
        reasons.append("MEDIAN_NOT_REACHED_WITHIN_OBSERVATION_WINDOW")
    if horizon is None:
        reasons.append("RMST_TAU_NOT_SUPPLIED_VALUE_IS_FOLLOW_UP_DEPENDENT")
    elif not reaches_tau:
        reasons.append("FOLLOW_UP_DOES_NOT_REACH_TAU")
        reasons.append("RMST_UNAVAILABLE_WITHOUT_OBSERVED_FOLLOW_UP_TO_TAU")

    # The computed accumulator is only an RMST when tau is explicit and the
    # sample reaches tau.  Otherwise publishing it under the RMST field would
    # disguise a data-dependent truncation or unsupported extrapolation.
    published_rmst = restricted_mean if horizon is not None and reaches_tau else None

    return QueueLifetimeDiagnostics(
        status=EvidenceStatus.UNCALIBRATED,
        sample_count=len(rows),
        observed_exits=exits_total,
        censored_count=censored_total,
        median_survival_seconds=median_survival,
        restricted_mean_survival_seconds=published_rmst,
        restricted_mean_tau_seconds=horizon,
        follow_up_reaches_tau=reaches_tau,
        curve=tuple(curve),
        calibrated=False,
        reasons=tuple(reasons),
    )
