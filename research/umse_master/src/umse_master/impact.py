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
    expected_price_change: float
    observed_price_change: float
    residual: float
    normalized_residual: float
    failed_response_score: float
    direction_consistent: bool
    calibrated: bool = False


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
    direction_consistent = expected == 0 or observed == 0 or (expected > 0) == (observed > 0)
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


def estimate_impact_decay(responses: Sequence[float]) -> ImpactDecay:
    xs = [abs(float(x)) for x in responses if math.isfinite(float(x))]
    if len(xs) < 3 or xs[0] <= 0:
        return ImpactDecay(None, 0.0, 0.0, False)
    ratios = []
    for a, b in zip(xs, xs[1:]):
        if a > 0 and b > 0:
            ratios.append(b / a)
    if not ratios:
        return ImpactDecay(None, 0.0, 0.0, False)
    # Geometric mean is robust to multiplicative decay. Growth/non-decay implies no finite half-life.
    log_mean = sum(math.log(max(r, 1e-12)) for r in ratios) / len(ratios)
    decay_ratio = math.exp(log_mean)
    if 0 < decay_ratio < 1:
        half_life = math.log(0.5) / math.log(decay_ratio)
        persistence = max(0.0, min(1.0, decay_ratio))
    else:
        half_life = None
        persistence = 1.0 if decay_ratio >= 1 else 0.0
    recovery_fraction = max(0.0, min(1.0, 1.0 - xs[-1] / xs[0]))
    return ImpactDecay(half_life, persistence, recovery_fraction, True)
