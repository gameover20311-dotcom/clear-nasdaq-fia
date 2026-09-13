from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from statistics import median
from typing import Sequence

from umse_master.liquidity import OrderBookSnapshot

from .contracts import EvidenceStatus


@dataclass(frozen=True)
class OrderBookMemory:
    status: EvidenceStatus
    sample_count: int
    duplicate_snapshots_dropped: int
    median_interval_seconds: float | None
    lag1_imbalance_correlation: float | None
    lag1_depth_correlation: float | None
    lag1_spread_correlation: float | None
    imbalance_half_life_steps: float | None
    approximate_half_life_seconds: float | None
    calibrated: bool
    reasons: tuple[str, ...]


def _corr(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y) or len(x) < 3:
        return None
    mx = sum(x) / len(x)
    my = sum(y) / len(y)
    vx = sum((a - mx) ** 2 for a in x)
    vy = sum((b - my) ** 2 for b in y)
    if vx <= 1e-15 or vy <= 1e-15:
        return None
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return max(-1.0, min(1.0, cov / math.sqrt(vx * vy)))


def _series(snapshot: OrderBookSnapshot) -> tuple[float, float, float]:
    bid = sum(float(x.size) for x in snapshot.bids)
    ask = sum(float(x.size) for x in snapshot.asks)
    gross = bid + ask
    imbalance = (bid - ask) / gross if gross > 0 else 0.0
    depth = gross
    spread = snapshot.spread_ticks
    return imbalance, depth, spread


def estimate_orderbook_memory(
    snapshots: Sequence[OrderBookSnapshot],
    decision_time_utc: datetime,
    *,
    max_lag_steps: int = 12,
    max_interval_cv: float = 0.50,
) -> OrderBookMemory:
    """Estimate descriptive book memory without pretending irregular samples are uniform.

    A step-based half-life is only converted to seconds when snapshot intervals are
    sufficiently regular. The threshold is an explicit protocol input, not a hidden
    calibration constant.
    """

    if max_lag_steps < 1:
        raise ValueError("max_lag_steps must be >= 1")
    if max_interval_cv < 0:
        raise ValueError("max_interval_cv must be >= 0")

    eligible = [s for s in snapshots if s.eligible_at(decision_time_utc)]
    eligible.sort(key=lambda s: (s.event_time_utc, s.provenance_id))

    # REPUBLICATION IS NOT MEMORY.
    # A feed that re-emits an unchanged book on a timer, a heartbeat, or a
    # recovery replay inserts consecutive identical states. Those drive the
    # lag-1 autocorrelation toward 1 and manufacture persistence that belongs
    # to the publishing cadence, not the market: the audit measured lag-1
    # imbalance moving from -0.0981 to +0.4565 on republication alone.
    deduped: list[OrderBookSnapshot] = []
    dropped = 0
    for snap in eligible:
        if deduped and _series(deduped[-1]) == _series(snap):
            dropped += 1
            continue
        deduped.append(snap)
    eligible = deduped
    if len(eligible) < 6:
        return OrderBookMemory(
            EvidenceStatus.INSUFFICIENT_DATA,
            len(eligible),
            dropped,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            ("AT_LEAST_6_CAUSAL_SNAPSHOTS_REQUIRED",),
        )

    values = [_series(s) for s in eligible]
    imbalance = [v[0] for v in values]
    depth = [v[1] for v in values]
    spread = [v[2] for v in values]

    lag1_i = _corr(imbalance[:-1], imbalance[1:])
    lag1_d = _corr(depth[:-1], depth[1:])
    lag1_s = _corr(spread[:-1], spread[1:])

    half_life_steps = None
    max_lag = min(max_lag_steps, len(imbalance) - 3)
    for lag in range(1, max_lag + 1):
        rho = _corr(imbalance[:-lag], imbalance[lag:])
        if rho is not None and rho <= 0.5:
            if lag == 1:
                half_life_steps = 1.0
            else:
                prev = _corr(imbalance[: -(lag - 1)], imbalance[lag - 1 :])
                if prev is None or prev == rho:
                    half_life_steps = float(lag)
                else:
                    frac = (prev - 0.5) / (prev - rho)
                    half_life_steps = (lag - 1) + max(0.0, min(1.0, frac))
            break

    intervals = [
        (b.event_time_utc - a.event_time_utc).total_seconds()
        for a, b in zip(eligible, eligible[1:])
        if b.event_time_utc > a.event_time_utc
    ]
    reasons: list[str] = []
    med_interval = median(intervals) if intervals else None
    half_life_seconds = None
    status = EvidenceStatus.UNCALIBRATED

    if med_interval is not None and intervals:
        mean_interval = sum(intervals) / len(intervals)
        variance = sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)
        cv = math.sqrt(variance) / mean_interval if mean_interval > 0 else math.inf
        if cv <= max_interval_cv and half_life_steps is not None:
            half_life_seconds = half_life_steps * med_interval
        elif cv > max_interval_cv:
            status = EvidenceStatus.DEGRADED
            reasons.append("IRREGULAR_SNAPSHOT_INTERVALS_STEP_TO_TIME_CONVERSION_REFUSED")

    if lag1_i is None:
        reasons.append("IMBALANCE_MEMORY_NOT_IDENTIFIABLE")
    if half_life_steps is None:
        reasons.append("HALF_LIFE_NOT_CROSSED_WITHIN_OBSERVED_LAGS")

    if dropped:
        reasons.append("DUPLICATE_SNAPSHOTS_DROPPED")

    return OrderBookMemory(
        status=status,
        sample_count=len(eligible),
        duplicate_snapshots_dropped=dropped,
        median_interval_seconds=med_interval,
        lag1_imbalance_correlation=lag1_i,
        lag1_depth_correlation=lag1_d,
        lag1_spread_correlation=lag1_s,
        imbalance_half_life_steps=half_life_steps,
        approximate_half_life_seconds=half_life_seconds,
        calibrated=False,
        reasons=tuple(reasons),
    )
