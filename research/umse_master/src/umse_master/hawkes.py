from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

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
    spectral_radius: Optional[float]
    spectral_radius_lower: float
    spectral_radius_upper: float
    stability: StabilityStatus
    subcritical: bool
    bounds_converged: bool
    # The Hawkes network is never fitted here; excitation and decay are
    # supplied by the caller. Nothing in this module calibrates them.
    calibrated: bool = False


SPECTRAL_SHIFT = 1.0
SPECTRAL_TOLERANCE = 1e-9
SPECTRAL_ITERATIONS = 4000


class StabilityStatus(str, Enum):
    SUBCRITICAL = "SUBCRITICAL"
    SUPERCRITICAL = "SUPERCRITICAL"
    INDETERMINATE = "INDETERMINATE"


def spectral_radius_bounds(
    matrix: Sequence[Sequence[float]],
    *,
    iterations: int = SPECTRAL_ITERATIONS,
    tolerance: float = SPECTRAL_TOLERANCE,
    shift: float = SPECTRAL_SHIFT,
) -> Tuple[float, float, bool]:
    """Rigorous two-sided bounds on the Perron root of a non-negative matrix.

    The previous implementation ran a fixed 200 power iterations with no
    convergence check and then took a Rayleigh quotient. For an imprimitive
    (cyclic) kernel power iteration does not converge, it oscillates, and the
    audit showed a kernel with true rho = 1.2599 reported as 0.6420 -- that is,
    an explosive network certified as stable.

    Two changes make this correct.

    First, iterate on M + shift*I instead of M. For a non-negative matrix
    rho(M + cI) = rho(M) + c exactly, and the shifted matrix has a strictly
    positive diagonal, which makes it primitive whenever M is irreducible and
    removes the oscillation entirely.

    Second, return Collatz-Wielandt bounds rather than a point estimate. For a
    non-negative matrix and any strictly positive v,
        min_i (Mv)_i / v_i  <=  rho(M)  <=  max_i (Mv)_i / v_i
    holds unconditionally, converged or not. The caller therefore gets a
    guaranteed enclosure, and a gap wider than `tolerance` is reported as
    non-convergence so the caller can fail closed instead of trusting a number.

    Returns (lower, upper, converged).
    """
    n = len(matrix)
    if n == 0:
        return 0.0, 0.0, True
    for row in matrix:
        for value in row:
            if not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError("spectral bounds require a finite non-negative matrix")
    if shift <= 0:
        raise ValueError("shift must be > 0")

    shifted = [[float(matrix[i][j]) + (shift if i == j else 0.0) for j in range(n)]
               for i in range(n)]
    v = [1.0] * n
    for _ in range(iterations):
        w = [sum(shifted[i][j] * v[j] for j in range(n)) for i in range(n)]
        norm = max(w)
        if norm <= 0:
            return 0.0, 0.0, True
        nxt = [x / norm for x in w]
        if max(abs(a - b) for a, b in zip(nxt, v)) <= tolerance:
            v = nxt
            break
        v = nxt

    # v stays strictly positive because the shifted diagonal is positive.
    w = [sum(shifted[i][j] * v[j] for j in range(n)) for i in range(n)]
    ratios = [w[i] / v[i] for i in range(n) if v[i] > 0]
    if not ratios:
        return 0.0, 0.0, False
    lower = min(ratios) - shift
    upper = max(ratios) - shift
    converged = (upper - lower) <= max(tolerance * 100.0, 1e-7)
    return max(0.0, lower), max(0.0, upper), converged


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
    lower, upper, converged = spectral_radius_bounds(integrated)
    # FAIL CLOSED: stability is claimed only when the guaranteed UPPER bound is
    # below 1. A kernel whose enclosure straddles 1, or whose bounds did not
    # converge, is INDETERMINATE and is never reported subcritical.
    if not converged:
        stability = StabilityStatus.INDETERMINATE
    elif upper < 1.0:
        stability = StabilityStatus.SUBCRITICAL
    elif lower >= 1.0:
        stability = StabilityStatus.SUPERCRITICAL
    else:
        stability = StabilityStatus.INDETERMINATE
    point = (lower + upper) / 2.0 if converged else None
    return HawkesDiagnostics(
        intensities={config.event_types[i].value: intensities[i] for i in range(len(config.event_types))},
        integrated_kernel=integrated,
        spectral_radius=point,
        spectral_radius_lower=lower,
        spectral_radius_upper=upper,
        stability=stability,
        subcritical=(stability == StabilityStatus.SUBCRITICAL),
        bounds_converged=converged,
        calibrated=False,
    )
