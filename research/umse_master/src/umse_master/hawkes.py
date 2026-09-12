from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Mapping, Sequence, Tuple

from .events import EventType, MarketEvent


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class HawkesNetworkConfig:
    event_types: Tuple[EventType, ...]
    baseline: Tuple[float, ...]
    excitation: Tuple[Tuple[float, ...], ...]
    decay: Tuple[Tuple[float, ...], ...]

    def __post_init__(self) -> None:
        n = len(self.event_types)
        if n == 0 or len(self.baseline) != n or len(self.excitation) != n or len(self.decay) != n:
            raise ValueError("Hawkes dimensions do not match event_types")
        if len(set(self.event_types)) != n:
            raise ValueError("event_types must be unique")
        for x in self.baseline:
            if not math.isfinite(float(x)) or x < 0:
                raise ValueError("baseline must be finite and >= 0")
        for arow, brow in zip(self.excitation, self.decay):
            if len(arow) != n or len(brow) != n:
                raise ValueError("Hawkes matrices must be square")
            for a, b in zip(arow, brow):
                if not math.isfinite(float(a)) or a < 0 or not math.isfinite(float(b)) or b <= 0:
                    raise ValueError("excitation must be >=0 and decay >0")


@dataclass(frozen=True)
class HawkesDiagnostics:
    intensities: Mapping[str, float]
    integrated_kernel: Tuple[Tuple[float, ...], ...]
    spectral_radius: float
    subcritical: bool
    calibrated: bool = False


def _spectral_radius_nonnegative(matrix: Sequence[Sequence[float]], iterations: int = 200) -> float:
    n = len(matrix)
    if n == 0:
        return 0.0
    v = [1.0 / n] * n
    lam = 0.0
    for _ in range(iterations):
        w = [sum(float(matrix[i][j]) * v[j] for j in range(n)) for i in range(n)]
        norm = max(abs(x) for x in w)
        if norm <= 1e-15:
            return 0.0
        v = [x / norm for x in w]
        lam = norm
    # Rayleigh-like estimate using the converged positive vector.
    w = [sum(float(matrix[i][j]) * v[j] for j in range(n)) for i in range(n)]
    numer = sum(v[i] * w[i] for i in range(n))
    denom = sum(x * x for x in v)
    return max(0.0, numer / denom if denom else lam)


def hawkes_diagnostics(
    config: HawkesNetworkConfig,
    events: Sequence[MarketEvent],
    decision_time_utc: datetime,
) -> HawkesDiagnostics:
    decision = _utc(decision_time_utc)
    idx = {event_type: i for i, event_type in enumerate(config.event_types)}
    intensities = [float(x) for x in config.baseline]
    for e in events:
        if e.event_type not in idx or not e.eligible_at(decision) or e.event_time_utc > decision:
            continue
        source_j = idx[e.event_type]
        dt_seconds = max(0.0, (decision - e.event_time_utc).total_seconds())
        for target_i in range(len(config.event_types)):
            alpha = config.excitation[target_i][source_j]
            beta = config.decay[target_i][source_j]
            intensities[target_i] += alpha * math.exp(-beta * dt_seconds)
    integrated = tuple(
        tuple(config.excitation[i][j] / config.decay[i][j] for j in range(len(config.event_types)))
        for i in range(len(config.event_types))
    )
    rho = _spectral_radius_nonnegative(integrated)
    return HawkesDiagnostics(
        intensities={config.event_types[i].value: intensities[i] for i in range(len(config.event_types))},
        integrated_kernel=integrated,
        spectral_radius=rho,
        subcritical=rho < 1.0,
        calibrated=False,
    )
