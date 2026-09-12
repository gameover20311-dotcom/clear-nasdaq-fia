from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Iterable, Mapping, Sequence, Tuple


class Scale(str, Enum):
    MICRO = "MICRO"
    MESO = "MESO"
    SESSION = "SESSION"
    H4 = "4H"
    H8 = "8H"


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class ScaleEvidence:
    scale: Scale
    timestamp_utc: datetime
    signed_signal: float
    quality: float
    persistence_minutes: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp_utc", _utc(self.timestamp_utc))
        if not math.isfinite(self.signed_signal) or self.signed_signal < -1 or self.signed_signal > 1:
            raise ValueError("signed_signal must be in [-1,1]")
        if not 0 <= self.quality <= 1 or self.persistence_minutes < 0:
            raise ValueError("invalid scale evidence")


@dataclass(frozen=True)
class CrossScaleReport:
    coherence: float
    information_half_life_minutes: float | None
    survival_to_4h: float
    survival_to_8h: float
    allow_4h_influence: bool
    allow_8h_influence: bool
    calibrated: bool = False


def estimate_half_life(values: Sequence[float], step_minutes: float) -> float | None:
    if len(values) < 3 or step_minutes <= 0:
        return None
    xs = [float(x) for x in values]
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs)
    if var <= 1e-12:
        return None
    cov = sum((xs[i] - mean) * (xs[i - 1] - mean) for i in range(1, len(xs)))
    rho = cov / var
    if not 0 < rho < 1:
        return None
    return -math.log(2.0) * step_minutes / math.log(rho)


def assess_cross_scale(
    evidence: Iterable[ScaleEvidence],
    *,
    half_life_minutes: float | None = None,
    min_quality: float = 0.5,
    min_survival: float = 0.2,
) -> CrossScaleReport:
    rows = tuple(evidence)
    if not rows:
        return CrossScaleReport(0.0, half_life_minutes, 0.0, 0.0, False, False, False)
    weighted = [r.signed_signal * r.quality for r in rows]
    gross = sum(abs(x) for x in weighted)
    coherence = abs(sum(weighted)) / gross if gross > 0 else 0.0
    quality = sum(r.quality for r in rows) / len(rows)
    persistence_hint = max((r.persistence_minutes for r in rows), default=0.0)
    hl = half_life_minutes if half_life_minutes is not None else (persistence_hint if persistence_hint > 0 else None)
    if hl is None or hl <= 0:
        s4 = s8 = 0.0
    else:
        s4 = math.exp(-math.log(2.0) * 240.0 / hl)
        s8 = math.exp(-math.log(2.0) * 480.0 / hl)
    s4 *= coherence * quality
    s8 *= coherence * quality
    return CrossScaleReport(
        coherence=max(0.0, min(1.0, coherence)),
        information_half_life_minutes=hl,
        survival_to_4h=max(0.0, min(1.0, s4)),
        survival_to_8h=max(0.0, min(1.0, s8)),
        allow_4h_influence=quality >= min_quality and s4 >= min_survival,
        allow_8h_influence=quality >= min_quality and s8 >= min_survival,
        calibrated=False,
    )
