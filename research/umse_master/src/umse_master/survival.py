from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence, Tuple


@dataclass(frozen=True)
class SurvivalPoint:
    time: float
    survival_probability: float
    hazard_at_time: float


@dataclass(frozen=True)
class StateSurvivalDiagnostics:
    curve: Tuple[SurvivalPoint, ...]
    median_duration: float | None
    mean_hazard: float
    metastability_score: float
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
    curve = kaplan_meier(durations, censored)
    if not curve:
        return StateSurvivalDiagnostics((), None, 0.0, 0.0, False)
    median = next((p.time for p in curve if p.survival_probability <= 0.5), None)
    mean_hazard = sum(p.hazard_at_time for p in curve) / len(curve)
    survival_at_target = 1.0
    for p in curve:
        if p.time <= target_duration:
            survival_at_target = p.survival_probability
        else:
            break
    metastability = max(0.0, min(1.0, survival_at_target * (1.0 - mean_hazard)))
    return StateSurvivalDiagnostics(curve, median, mean_hazard, metastability, False)
