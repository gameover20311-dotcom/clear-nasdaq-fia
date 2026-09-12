from __future__ import annotations

from dataclasses import dataclass
import math


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _clip11(x: float) -> float:
    return max(-1.0, min(1.0, float(x)))


@dataclass(frozen=True)
class AgentPressureInference:
    urgency: float
    signed_inventory_pressure: float
    informed_flow_likelihood: float
    forced_flow_likelihood: float
    passive_absorption_likelihood: float
    identifiability_score: float
    direct_agent_identity_identifiable: bool = False
    calibrated: bool = False
    predictive: bool = False


def infer_agent_pressure(
    *,
    aggression_imbalance: float,
    signed_price_response: float,
    failed_response_score: float,
    liquidity_thinness: float,
    replenishment_ratio: float,
    persistence: float,
    true_mbo_identity_fraction: float = 0.0,
) -> AgentPressureInference:
    for name, x in {
        "aggression_imbalance": aggression_imbalance,
        "signed_price_response": signed_price_response,
    }.items():
        if not math.isfinite(float(x)) or not -1 <= float(x) <= 1:
            raise ValueError(f"{name} must be in [-1,1]")
    for name, x in {
        "failed_response_score": failed_response_score,
        "liquidity_thinness": liquidity_thinness,
        "replenishment_ratio": replenishment_ratio,
        "persistence": persistence,
        "true_mbo_identity_fraction": true_mbo_identity_fraction,
    }.items():
        if not math.isfinite(float(x)) or not 0 <= float(x) <= 1:
            raise ValueError(f"{name} must be in [0,1]")
    urgency = _clip01(abs(aggression_imbalance) * (0.6 + 0.4 * liquidity_thinness) + 0.25 * persistence)
    signed_inventory = _clip11(0.65 * aggression_imbalance + 0.35 * signed_price_response)
    alignment = _clip01((1.0 + aggression_imbalance * signed_price_response) / 2.0)
    informed = _clip01(alignment * (1.0 - failed_response_score) * (0.5 + 0.5 * persistence))
    forced = _clip01(urgency * liquidity_thinness * (1.0 - replenishment_ratio))
    passive = _clip01(failed_response_score * replenishment_ratio * (1.0 - liquidity_thinness / 2.0))
    # MBO identity improves observability of order behaviour but still does not reveal trader identity.
    identifiability = _clip01(0.25 + 0.5 * true_mbo_identity_fraction + 0.25 * persistence)
    return AgentPressureInference(
        urgency=urgency,
        signed_inventory_pressure=signed_inventory,
        informed_flow_likelihood=informed,
        forced_flow_likelihood=forced,
        passive_absorption_likelihood=passive,
        identifiability_score=identifiability,
        direct_agent_identity_identifiable=False,
        calibrated=False,
        predictive=False,
    )
