"""Latent mechanism competition for UMSE V2.

This module ranks *hypotheses* about the mechanism that could explain an
observed market state.  It deliberately does not identify traders, infer a
strategic equilibrium, or turn the ranking into a forecast probability.

The scores are transparent research heuristics.  They can be useful for
falsification and for deciding which mechanisms deserve later calibration, but
`calibrated` and `predictive` remain False by construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Mapping

from .contracts import EvidenceStatus


class Mechanism(str, Enum):
    INFORMED_BUYING = "INFORMED_BUYING"
    INFORMED_SELLING = "INFORMED_SELLING"
    SHORT_COVERING = "SHORT_COVERING"
    LONG_LIQUIDATION = "LONG_LIQUIDATION"
    PASSIVE_ACCUMULATION = "PASSIVE_ACCUMULATION"
    PASSIVE_DISTRIBUTION = "PASSIVE_DISTRIBUTION"
    LIQUIDITY_VACUUM_UP = "LIQUIDITY_VACUUM_UP"
    LIQUIDITY_VACUUM_DOWN = "LIQUIDITY_VACUUM_DOWN"
    BID_ABSORPTION = "BID_ABSORPTION"
    ASK_ABSORPTION = "ASK_ABSORPTION"
    BALANCED_NOISE = "BALANCED_NOISE"


def _unit(name: str, value: float) -> float:
    x = float(value)
    if not math.isfinite(x) or not 0.0 <= x <= 1.0:
        raise ValueError(f"{name} must be finite and in [0,1]")
    return x


def _signed(name: str, value: float) -> float:
    x = float(value)
    if not math.isfinite(x) or not -1.0 <= x <= 1.0:
        raise ValueError(f"{name} must be finite and in [-1,1]")
    return x


@dataclass(frozen=True)
class MechanismEvidence:
    """Normalized descriptive evidence available at one decision time.

    Positive signed values mean upward/buy-side pressure, negative values mean
    downward/sell-side pressure.  `information_lead` is a descriptive lead/lag
    screen, not a causal or predictive claim.
    """

    aggression_imbalance: float
    signed_price_response: float
    failed_response_score: float
    liquidity_thinness: float
    bid_replenishment: float
    ask_replenishment: float
    queue_exit_asymmetry: float
    information_lead: float
    stress: float
    source_status: EvidenceStatus = EvidenceStatus.UNCALIBRATED

    def __post_init__(self) -> None:
        for name in (
            "aggression_imbalance",
            "signed_price_response",
            "queue_exit_asymmetry",
            "information_lead",
        ):
            _signed(name, getattr(self, name))
        for name in (
            "failed_response_score",
            "liquidity_thinness",
            "bid_replenishment",
            "ask_replenishment",
            "stress",
        ):
            _unit(name, getattr(self, name))


@dataclass(frozen=True)
class MechanismCompetition:
    status: EvidenceStatus
    weights: Mapping[Mechanism, float]
    leading_hypothesis: Mechanism | None
    leading_weight: float | None
    separation: float | None
    entropy: float | None
    reasons: tuple[str, ...]
    calibrated: bool = False
    predictive: bool = False
    trader_identity_identifiable: bool = False
    strategic_equilibrium_identified: bool = False

    def __post_init__(self) -> None:
        if self.calibrated or self.predictive:
            raise ValueError("mechanism competition is descriptive research only")
        if self.trader_identity_identifiable or self.strategic_equilibrium_identified:
            raise ValueError("market mechanism evidence cannot identify traders/equilibria")
        if self.weights:
            total = sum(float(v) for v in self.weights.values())
            if abs(total - 1.0) > 1e-9:
                raise ValueError("mechanism weights must sum to one")


def _softmax(scores: Mapping[Mechanism, float]) -> dict[Mechanism, float]:
    peak = max(scores.values())
    exps = {k: math.exp(v - peak) for k, v in scores.items()}
    total = sum(exps.values())
    return {k: v / total for k, v in exps.items()}


def compete_mechanisms(e: MechanismEvidence) -> MechanismCompetition:
    """Rank mutually competing market-mechanism hypotheses.

    The result is intentionally *not* a posterior probability.  Softmax is used
    only to make heterogeneous scores comparable on a common simplex.
    """

    if e.source_status in {
        EvidenceStatus.INSUFFICIENT_DATA,
        EvidenceStatus.PROTOCOL_INELIGIBLE,
        EvidenceStatus.NOT_IDENTIFIABLE,
    }:
        return MechanismCompetition(
            status=e.source_status,
            weights={},
            leading_hypothesis=None,
            leading_weight=None,
            separation=None,
            entropy=None,
            reasons=("SOURCE_EVIDENCE_NOT_ADEQUATE_FOR_MECHANISM_COMPETITION",),
        )

    a = e.aggression_imbalance
    r = e.signed_price_response
    f = e.failed_response_score
    thin = e.liquidity_thinness
    br = e.bid_replenishment
    ar = e.ask_replenishment
    q = e.queue_exit_asymmetry
    lead = e.information_lead
    stress = e.stress

    buy = max(0.0, a)
    sell = max(0.0, -a)
    up = max(0.0, r)
    down = max(0.0, -r)
    lead_up = max(0.0, lead)
    lead_down = max(0.0, -lead)
    bid_exit = max(0.0, -q)
    ask_exit = max(0.0, q)

    scores = {
        Mechanism.INFORMED_BUYING: 1.25 * buy + 1.00 * up + 0.65 * lead_up + 0.35 * (1.0 - f),
        Mechanism.INFORMED_SELLING: 1.25 * sell + 1.00 * down + 0.65 * lead_down + 0.35 * (1.0 - f),
        Mechanism.SHORT_COVERING: 0.90 * up + 0.75 * ask_exit + 0.70 * stress + 0.45 * thin - 0.35 * buy,
        Mechanism.LONG_LIQUIDATION: 0.90 * down + 0.75 * bid_exit + 0.70 * stress + 0.45 * thin - 0.35 * sell,
        Mechanism.PASSIVE_ACCUMULATION: 1.05 * f + 0.95 * br + 0.45 * sell + 0.30 * max(0.0, r),
        Mechanism.PASSIVE_DISTRIBUTION: 1.05 * f + 0.95 * ar + 0.45 * buy + 0.30 * max(0.0, -r),
        Mechanism.LIQUIDITY_VACUUM_UP: 1.15 * thin + 0.85 * up + 0.55 * ask_exit + 0.30 * stress,
        Mechanism.LIQUIDITY_VACUUM_DOWN: 1.15 * thin + 0.85 * down + 0.55 * bid_exit + 0.30 * stress,
        Mechanism.BID_ABSORPTION: 1.10 * f + 1.00 * br + 0.60 * sell + 0.35 * max(0.0, r),
        Mechanism.ASK_ABSORPTION: 1.10 * f + 1.00 * ar + 0.60 * buy + 0.35 * max(0.0, -r),
        Mechanism.BALANCED_NOISE: 1.20 * (1.0 - abs(a)) + 0.80 * (1.0 - abs(r)) + 0.55 * (1.0 - stress),
    }

    weights = _softmax(scores)
    ranked = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    lead_mech, lead_weight = ranked[0]
    separation = lead_weight - ranked[1][1]
    entropy = -sum(p * math.log(p) for p in weights.values() if p > 0.0) / math.log(len(weights))

    reasons: list[str] = [
        "WEIGHTS_ARE_HYPOTHESIS_COMPETITION_NOT_POSTERIOR_PROBABILITIES",
        "NO_TRADER_IDENTITY_OR_GAME_EQUILIBRIUM_CLAIM",
    ]
    if separation < 0.05:
        reasons.append("NO_CLEAR_MECHANISM_SEPARATION")
    if entropy > 0.90:
        reasons.append("HIGH_MECHANISM_AMBIGUITY")

    return MechanismCompetition(
        status=EvidenceStatus.UNCALIBRATED,
        weights=weights,
        leading_hypothesis=lead_mech,
        leading_weight=lead_weight,
        separation=separation,
        entropy=entropy,
        reasons=tuple(reasons),
        calibrated=False,
        predictive=False,
        trader_identity_identifiable=False,
        strategic_equilibrium_identified=False,
    )
