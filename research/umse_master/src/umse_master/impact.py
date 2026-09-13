from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Optional, Sequence


@dataclass(frozen=True)
class ImpactModelConfig:
    eta: float = 1.0
    alpha: float = 0.5
    volatility_weight: float = 0.5
    resilience_weight: float = 0.5
    epsilon: float = 1e-9

    def __post_init__(self) -> None:
        if self.eta < 0 or self.alpha <= 0 or self.epsilon <= 0:
            raise ValueError("invalid impact model configuration")


@dataclass(frozen=True)
class ImpactContext:
    signed_aggressive_volume: float
    effective_liquidity: float
    realized_volatility: float
    resilience: float

    def __post_init__(self) -> None:
        for name in ("signed_aggressive_volume", "effective_liquidity", "realized_volatility", "resilience"):
            if not math.isfinite(float(getattr(self, name))):
                raise ValueError(f"{name} must be finite")
        if self.effective_liquidity < 0 or self.realized_volatility < 0:
            raise ValueError("liquidity and volatility must be >= 0")
        if not 0 <= self.resilience <= 1:
            raise ValueError("resilience must be in [0,1]")


@dataclass(frozen=True)
class ResponseSurprise:
    # UNCALIBRATED. `eta` defaults to 1.0 and is not fitted, so `expected` is a
    # participation-scaled quantity, not a price in index points, and the
    # residual against an observed price change is dimensionally meaningless
    # until eta is calibrated on real data. Retained as a research diagnostic
    # and explicitly not promotion eligible.
    expected_price_change: float
    observed_price_change: float
    residual: float
    normalized_residual: float
    failed_response_score: float
    direction_consistent: bool
    calibrated: bool = False
    eta_calibrated: bool = False
    promotion_eligible: bool = False
    status: str = "UNCALIBRATED_NOT_PROMOTION_ELIGIBLE"


def expected_price_impact(ctx: ImpactContext, config: ImpactModelConfig = ImpactModelConfig()) -> float:
    q = float(ctx.signed_aggressive_volume)
    if q == 0:
        return 0.0
    side = 1.0 if q > 0 else -1.0
    participation = abs(q) / (ctx.effective_liquidity + config.epsilon)
    nonlinear = participation ** config.alpha
    vol_term = 1.0 + config.volatility_weight * ctx.realized_volatility
    resilience_term = 1.0 + config.resilience_weight * ctx.resilience
    return side * config.eta * nonlinear * vol_term / resilience_term


def compute_response_surprise(
    observed_price_change: float,
    ctx: ImpactContext,
    config: ImpactModelConfig = ImpactModelConfig(),
) -> ResponseSurprise:
    observed = float(observed_price_change)
    if not math.isfinite(observed):
        raise ValueError("observed_price_change must be finite")
    expected = expected_price_impact(ctx, config)
    residual = observed - expected
    scale = abs(expected) + max(config.epsilon, ctx.realized_volatility)
    normalized = residual / scale
    # A zero move is a FAILED response, not a consistent one. The previous
    # expression returned True for observed == 0, which mislabelled exactly the
    # case the failed-response detector exists to find.
    direction_consistent = expected == 0 or (observed != 0 and (expected > 0) == (observed > 0))
    # Failed response asks: strong signed flow expected movement, but movement was absent or opposite.
    expected_strength = abs(expected) / (abs(expected) + 1.0)
    if expected == 0:
        failed = 0.0
    else:
        realized_fraction = max(-1.0, min(1.0, observed / (abs(expected) + config.epsilon) * (1 if expected > 0 else -1)))
        failed = expected_strength * (1.0 - max(0.0, realized_fraction))
    return ResponseSurprise(
        expected_price_change=expected,
        observed_price_change=observed,
        residual=residual,
        normalized_residual=normalized,
        failed_response_score=max(0.0, min(1.0, failed)),
        direction_consistent=direction_consistent,
        calibrated=False,
    )


@dataclass(frozen=True)
class ImpactDecay:
    half_life_steps: Optional[float]
    persistence_score: float
    recovery_fraction: float
    identifiable: bool
    fit_r_squared: float = 0.0
    log_slope_per_step: Optional[float] = None
    sign_reversals: int = 0
    monotone_decay: bool = False
    calibrated: bool = False


MIN_DECAY_FIT_R2 = 0.90


def estimate_impact_decay(responses: Sequence[float]) -> ImpactDecay:
    """Half-life of an impact response path, fitted over the WHOLE path.

    The previous implementation took the geometric mean of consecutive ratios.
    That telescopes exactly: mean(log(x[i+1]/x[i])) == log(x[-1]/x[0])/(n-1), so
    only the two endpoints mattered. The audit showed [8, 4, 2, 1] and
    [8, 1000, 0.001, 1] both returning a half-life of 1.0, and the in-code
    comment claimed the geometric mean was "robust to multiplicative decay",
    which is the reverse of the truth.

    Fitting log|x| against t by least squares uses every point and yields an
    R^2 that reveals how badly the exponential model fits. A path that is not
    close to exponential is now reported as unidentifiable instead of being
    assigned a manufactured half-life.

    Sign is destroyed by the absolute value, as before, so `sign_reversals`
    records how often the response actually flipped -- a reversal is not decay.
    """
    raw = [float(x) for x in responses if math.isfinite(float(x))]
    xs = [abs(x) for x in raw]
    if len(xs) < 3 or xs[0] <= 0:
        return ImpactDecay(None, 0.0, 0.0, False)

    reversals = sum(
        1 for a, b in zip(raw, raw[1:]) if a != 0 and b != 0 and (a > 0) != (b > 0)
    )

    points = [(i, math.log(v)) for i, v in enumerate(xs) if v > 0]
    if len(points) < 3:
        return ImpactDecay(None, 0.0, 0.0, False, sign_reversals=reversals)

    n = len(points)
    mean_t = sum(t for t, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    stt = sum((t - mean_t) ** 2 for t, _ in points)
    if stt <= 1e-12:
        return ImpactDecay(None, 0.0, 0.0, False, sign_reversals=reversals)
    slope = sum((t - mean_t) * (y - mean_y) for t, y in points) / stt
    intercept = mean_y - slope * mean_t
    ss_res = sum((y - (intercept + slope * t)) ** 2 for t, y in points)
    ss_tot = sum((y - mean_y) ** 2 for _, y in points)
    r_squared = 1.0 if ss_tot <= 1e-12 else max(0.0, 1.0 - ss_res / ss_tot)

    monotone = all(b <= a + 1e-12 for a, b in zip(xs, xs[1:]))
    well_fitted = r_squared >= MIN_DECAY_FIT_R2

    if not well_fitted:
        # The path is not exponential. Report that rather than invent a decay.
        return ImpactDecay(
            None, 0.0,
            max(0.0, min(1.0, 1.0 - xs[-1] / xs[0])),
            False, r_squared, slope, reversals, monotone,
        )

    if slope < 0:
        half_life = math.log(2.0) / (-slope)
        persistence = max(0.0, min(1.0, math.exp(slope)))
    else:
        half_life = None
        persistence = 1.0

    return ImpactDecay(
        half_life_steps=half_life,
        persistence_score=persistence,
        recovery_fraction=max(0.0, min(1.0, 1.0 - xs[-1] / xs[0])),
        identifiable=True,
        fit_r_squared=r_squared,
        log_slope_per_step=slope,
        sign_reversals=reversals,
        monotone_decay=monotone,
        calibrated=False,
    )
