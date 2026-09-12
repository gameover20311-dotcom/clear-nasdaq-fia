from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Mapping

from .contracts import MarketState, Mechanism


def _softmax(scores: Mapping[str, float]) -> Dict[str, float]:
    m = max(scores.values()) if scores else 0.0
    exps = {k: math.exp(v - m) for k, v in scores.items()}
    total = sum(exps.values()) or 1.0
    return {k: v / total for k, v in exps.items()}


def _get(weights: Mapping[str, float], key: Mechanism) -> float:
    return float(weights.get(key.value, 0.0))


@dataclass(frozen=True)
class StateEvidence:
    mechanism_weights: Mapping[str, float]
    criticality: float
    resilience: float
    liquidity_thinness: float
    volatility_stress: float
    structural_entropy: float

    def __post_init__(self) -> None:
        for name in ("criticality", "resilience", "liquidity_thinness", "volatility_stress", "structural_entropy"):
            x = float(getattr(self, name))
            if not math.isfinite(x) or x < 0 or x > 1:
                raise ValueError(f"{name} must be in [0,1]")


@dataclass(frozen=True)
class StateInference:
    state_weights: Mapping[str, float]
    top_state: str
    entropy: float
    calibrated: bool = False
    predictive: bool = False


def _normalized_entropy(weights: Mapping[str, float]) -> float:
    vals = [max(1e-15, float(x)) for x in weights.values()]
    h = -sum(p * math.log(p) for p in vals)
    return h / math.log(len(vals)) if len(vals) > 1 else 0.0


def infer_state(e: StateEvidence) -> StateInference:
    m = e.mechanism_weights
    informed_buy = _get(m, Mechanism.INFORMED_BUYING)
    informed_sell = _get(m, Mechanism.INFORMED_SELLING)
    scores = {
        MarketState.BALANCED_AUCTION.value: 1.4 * _get(m, Mechanism.BALANCED_NOISE) + e.resilience + (1 - e.criticality),
        MarketState.INFORMED_ACCUMULATION.value: 1.3 * informed_buy + _get(m, Mechanism.PASSIVE_ACCUMULATION) + 0.5 * e.resilience,
        MarketState.DISTRIBUTION.value: 1.3 * informed_sell + _get(m, Mechanism.PASSIVE_DISTRIBUTION) + 0.5 * e.resilience,
        MarketState.LIQUIDITY_VACUUM.value: 1.4 * _get(m, Mechanism.LIQUIDITY_VACUUM) + e.liquidity_thinness + 0.5 * e.criticality,
        MarketState.SHORT_COVERING.value: 1.5 * _get(m, Mechanism.SHORT_COVERING) + 0.5 * e.volatility_stress,
        MarketState.FORCED_LIQUIDATION.value: 1.5 * _get(m, Mechanism.LONG_LIQUIDATION) + 0.5 * e.volatility_stress,
        MarketState.DIRECTIONAL_CASCADE.value: 1.2 * max(informed_buy, informed_sell) + 1.3 * e.criticality + 0.8 * e.volatility_stress,
        MarketState.ABSORPTION.value: 1.6 * _get(m, Mechanism.ABSORPTION) + e.resilience,
        MarketState.TRANSITION.value: 1.0 * e.criticality + 0.8 * e.structural_entropy + 0.6 * e.volatility_stress,
        MarketState.CHAOS_UNCERTAIN.value: 1.2 * e.structural_entropy + 0.8 * e.volatility_stress + 0.5 * e.criticality,
    }
    weights = _softmax(scores)
    return StateInference(weights, max(weights, key=weights.get), _normalized_entropy(weights), False, False)
