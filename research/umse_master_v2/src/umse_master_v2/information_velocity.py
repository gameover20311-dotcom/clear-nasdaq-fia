from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from statistics import median
from typing import Iterable

from .contracts import EvidenceStatus


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class TimedShock:
    node: str
    event_time_utc: datetime
    available_time_utc: datetime
    provenance_id: str
    magnitude: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time_utc", _utc(self.event_time_utc))
        object.__setattr__(self, "available_time_utc", _utc(self.available_time_utc))
        if not self.node.strip() or not self.provenance_id.strip():
            raise ValueError("node and provenance_id must be non-empty")
        if not math.isfinite(float(self.magnitude)):
            raise ValueError("magnitude must be finite")

    def eligible_at(self, decision_time_utc: datetime) -> bool:
        decision = _utc(decision_time_utc)
        return self.event_time_utc <= decision and self.available_time_utc <= decision


@dataclass(frozen=True)
class InformationVelocityReport:
    status: EvidenceStatus
    source_node: str
    target_node: str
    matched_pairs: int
    median_lag_seconds: float | None
    propagation_rate_per_second: float | None
    magnitude_correlation: float | None
    simultaneous_pairs: int
    directional_claim_allowed: bool
    calibrated: bool
    reasons: tuple[str, ...]


def _corr(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 1e-15 or vy <= 1e-15:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return max(-1.0, min(1.0, cov / math.sqrt(vx * vy)))


def estimate_information_velocity(
    shocks: Iterable[TimedShock],
    decision_time_utc: datetime,
    *,
    source_node: str,
    target_node: str,
    max_lag_seconds: float,
    minimum_pairs: int = 5,
) -> InformationVelocityReport:
    """Descriptive lead-lag matcher; never a causal proof by itself.

    Each source shock is paired to the earliest *subsequent* target shock inside
    the declared lag window. Simultaneous events are counted but excluded from a
    directional lead-lag claim because timestamp resolution cannot establish order.
    """

    if source_node == target_node:
        raise ValueError("source_node and target_node must differ")
    if max_lag_seconds <= 0 or not math.isfinite(float(max_lag_seconds)):
        raise ValueError("max_lag_seconds must be finite and > 0")
    if minimum_pairs < 3:
        raise ValueError("minimum_pairs must be >= 3")

    decision = _utc(decision_time_utc)
    rows = [s for s in shocks if s.eligible_at(decision)]
    src = sorted((s for s in rows if s.node == source_node), key=lambda s: (s.event_time_utc, s.provenance_id))
    tgt = sorted((s for s in rows if s.node == target_node), key=lambda s: (s.event_time_utc, s.provenance_id))

    used_targets: set[str] = set()
    lags: list[float] = []
    sx: list[float] = []
    ty: list[float] = []
    simultaneous = 0

    for s in src:
        best = None
        for t in tgt:
            if t.provenance_id in used_targets:
                continue
            lag = (t.event_time_utc - s.event_time_utc).total_seconds()
            if lag < 0:
                continue
            if lag > max_lag_seconds:
                break
            best = (t, lag)
            break
        if best is None:
            continue
        t, lag = best
        used_targets.add(t.provenance_id)
        if lag == 0:
            simultaneous += 1
            continue
        lags.append(lag)
        sx.append(float(s.magnitude))
        ty.append(float(t.magnitude))

    if len(lags) < minimum_pairs:
        return InformationVelocityReport(
            status=EvidenceStatus.INSUFFICIENT_DATA,
            source_node=source_node,
            target_node=target_node,
            matched_pairs=len(lags),
            median_lag_seconds=median(lags) if lags else None,
            propagation_rate_per_second=None,
            magnitude_correlation=_corr(sx, ty),
            simultaneous_pairs=simultaneous,
            directional_claim_allowed=False,
            calibrated=False,
            reasons=("INSUFFICIENT_NON_SIMULTANEOUS_PAIRS", "DESCRIPTIVE_NOT_CAUSAL_PROOF"),
        )

    med = float(median(lags))
    rate = 1.0 / med if med > 0 else None
    return InformationVelocityReport(
        status=EvidenceStatus.UNCALIBRATED,
        source_node=source_node,
        target_node=target_node,
        matched_pairs=len(lags),
        median_lag_seconds=med,
        propagation_rate_per_second=rate,
        magnitude_correlation=_corr(sx, ty),
        simultaneous_pairs=simultaneous,
        directional_claim_allowed=True,
        calibrated=False,
        reasons=("DESCRIPTIVE_LEAD_LAG_REQUIRES_NULL_AND_LATENCY_CONTROL",),
    )
