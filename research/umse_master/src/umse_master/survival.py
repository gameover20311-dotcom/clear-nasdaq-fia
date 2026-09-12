from __future__ import annotations

from dataclasses import dataclass
import math
from enum import Enum
from typing import Iterable, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SurvivalPoint:
    time: float
    survival_probability: float
    hazard_at_time: float


class SurvivalStatus(str, Enum):
    OBSERVED = "OBSERVED"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    NOT_IDENTIFIABLE_ALL_CENSORED = "NOT_IDENTIFIABLE_ALL_CENSORED"


@dataclass(frozen=True)
class StateSurvivalDiagnostics:
    curve: Tuple[SurvivalPoint, ...]
    median_duration: float | None
    mean_hazard: Optional[float]
    metastability_score: Optional[float]
    status: SurvivalStatus = SurvivalStatus.OBSERVED
    observed_events: int = 0
    censored_count: int = 0
    calibrated: bool = False


def kaplan_meier(durations: Sequence[float], censored: Sequence[bool] | None = None) -> Tuple[SurvivalPoint, ...]:
    if not durations:
        return ()
    ds = [float(x) for x in durations]
    if any((not math.isfinite(x) or x <= 0) for x in ds):
        raise ValueError("durations must be finite and > 0")
    cs = list(censored) if censored is not None else [False] * len(ds)
    if len(cs) != len(ds):
        raise ValueError("censored length mismatch")
    rows = sorted(zip(ds, cs), key=lambda x: x[0])
    unique_times = sorted({d for d, _ in rows})
    survival = 1.0
    out = []
    for t in unique_times:
        at_risk = sum(1 for d, _ in rows if d >= t)
        events = sum(1 for d, c in rows if d == t and not c)
        if at_risk <= 0:
            continue
        hazard = events / at_risk
        survival *= 1.0 - hazard
        out.append(SurvivalPoint(t, max(0.0, survival), hazard))
    return tuple(out)


def analyze_state_survival(
    durations: Sequence[float],
    censored: Sequence[bool] | None = None,
    *,
    target_duration: float = 240.0,
) -> StateSurvivalDiagnostics:
    """Kaplan-Meier survival with UNKNOWN kept distinct from OBSERVED_LOW.

    The previous implementation returned metastability 1.0 when every
    observation was censored. No transition was ever observed in that case, so
    survival never decremented and mean hazard was 0 -- absence of evidence was
    rendered as maximum observed stability, the most costly direction for the
    error to run.

    A sample with no uncensored event now returns None with an explicit
    NOT_IDENTIFIABLE_ALL_CENSORED status. A genuinely short-lived state returns
    a low score with status OBSERVED. Those two are different claims and are no
    longer expressed by the same number.
    """
    rows = list(durations)
    flags = list(censored) if censored is not None else [False] * len(rows)
    if censored is not None and len(flags) != len(rows):
        raise ValueError("censored length mismatch")
    observed_events = sum(1 for c in flags if not c)
    censored_count = sum(1 for c in flags if c)

    if not rows:
        return StateSurvivalDiagnostics(
            (), None, None, None, SurvivalStatus.INSUFFICIENT_SAMPLE, 0, 0, False)

    curve = kaplan_meier(rows, flags)
    if observed_events == 0 or not curve:
        return StateSurvivalDiagnostics(
            curve, None, None, None,
            SurvivalStatus.NOT_IDENTIFIABLE_ALL_CENSORED,
            observed_events, censored_count, False)

    median = next((p.time for p in curve if p.survival_probability <= 0.5), None)
    mean_hazard = sum(p.hazard_at_time for p in curve) / len(curve)
    survival_at_target = 1.0
    for p in curve:
        if p.time <= target_duration:
            survival_at_target = p.survival_probability
        else:
            break
    metastability = max(0.0, min(1.0, survival_at_target * (1.0 - mean_hazard)))
    return StateSurvivalDiagnostics(
        curve, median, mean_hazard, metastability, SurvivalStatus.OBSERVED,
        observed_events, censored_count, False)
