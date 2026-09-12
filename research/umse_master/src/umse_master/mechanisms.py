from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Mapping

from .contracts import Mechanism


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _softmax(scores: Mapping[str, float]) -> Dict[str, float]:
    m = max(scores.values()) if scores else 0.0
    exps = {k: math.exp(v - m) for k, v in scores.items()}
    total = sum(exps.values()) or 1.0
    return {k: v / total for k, v in exps.items()}


@dataclass(frozen=True)
class MechanismEvidence:
    aggression_imbalance: float
    price_response_signed: float
    replenishment_ratio: float
    depth_imbalance: float
    resilience: float
    failed_response_score: float
    liquidity_thinness: float
    volatility_stress: float
    short_covering_context: float = 0.0
    forced_liquidation_context: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "aggression_imbalance",
            "price_response_signed",
            "depth_imbalance",
        ):
            x = float(getattr(self, name))
            if not math.isfinite(x) or x < -1 or x > 1:
                raise ValueError(f"{name} must be finite in [-1,1]")
        for name in (
            "replenishment_ratio",
            "resilience",
            "failed_response_score",
            "liquidity_thinness",
            "volatility_stress",
            "short_covering_context",
            "forced_liquidation_context",
        ):
            x = float(getattr(self, name))
            if not math.isfinite(x) or x < 0 or x > 1:
                raise ValueError(f"{name} must be finite in [0,1]")


@dataclass(frozen=True)
class MechanismCompetition:
    hypothesis_weights: Mapping[str, float]
    top_mechanism: str
    concentration: float
    calibrated: bool = False
    predictive: bool = False


def compete_mechanisms(e: MechanismEvidence) -> MechanismCompetition:
    buy = max(0.0, e.aggression_imbalance)
    sell = max(0.0, -e.aggression_imbalance)
    up = max(0.0, e.price_response_signed)
    down = max(0.0, -e.price_response_signed)
    absorb = e.failed_response_score * e.replenishment_ratio
    scores = {
        Mechanism.INFORMED_BUYING.value: 1.2 * buy + 0.8 * up + 0.4 * (1 - e.liquidity_thinness),
        Mechanism.INFORMED_SELLING.value: 1.2 * sell + 0.8 * down + 0.4 * (1 - e.liquidity_thinness),
        Mechanism.SHORT_COVERING.value: 1.0 * buy + 0.8 * up + 1.2 * e.short_covering_context + 0.5 * e.liquidity_thinness,
        Mechanism.LONG_LIQUIDATION.value: 1.0 * sell + 0.8 * down + 1.2 * e.forced_liquidation_context + 0.5 * e.liquidity_thinness,
        Mechanism.PASSIVE_ACCUMULATION.value: 0.8 * max(0.0, e.depth_imbalance) + 0.8 * e.replenishment_ratio + 0.8 * absorb,
        Mechanism.PASSIVE_DISTRIBUTION.value: 0.8 * max(0.0, -e.depth_imbalance) + 0.8 * e.replenishment_ratio + 0.8 * absorb,
        Mechanism.LIQUIDITY_VACUUM.value: 1.4 * e.liquidity_thinness + 0.8 * e.volatility_stress + 0.5 * (1 - e.resilience),
        Mechanism.ABSORPTION.value: 1.5 * absorb + 0.6 * e.resilience,
        Mechanism.BALANCED_NOISE.value: 1.2 * (1 - abs(e.aggression_imbalance)) + 0.8 * (1 - abs(e.price_response_signed)) + 0.5 * e.resilience,
    }
    weights = _softmax(scores)
    top = max(weights, key=weights.get)
    concentration = max(weights.values()) if weights else 0.0
    return MechanismCompetition(weights, top, concentration, calibrated=False, predictive=False)
