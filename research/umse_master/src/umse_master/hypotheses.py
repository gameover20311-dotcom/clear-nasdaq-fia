from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class HypothesisTier(str, Enum):
    ESSENTIAL = "ESSENTIAL"
    PLAUSIBLE_BUT_UNPROVEN = "PLAUSIBLE_BUT_UNPROVEN"
    REDUNDANT_RISK = "REDUNDANT_RISK"
    SPECULATIVE = "SPECULATIVE"
    NOT_IDENTIFIABLE_WITH_CURRENT_DATA = "NOT_IDENTIFIABLE_WITH_CURRENT_DATA"


@dataclass(frozen=True)
class ResearchHypothesis:
    name: str
    tier: HypothesisTier
    statement: str
    required_data: Tuple[str, ...]
    falsification_rule: str
    promotion_requirement: str


MASTER_HYPOTHESES: Tuple[ResearchHypothesis, ...] = (
    ResearchHypothesis(
        "queue_survival_liquidity_credibility",
        HypothesisTier.PLAUSIBLE_BUT_UNPROVEN,
        "Individual-order survival and replenishment persistence add information beyond aggregate depth.",
        ("true CME MBO order identity",),
        "Reject if queue metrics add no incremental unseen information versus L2 liquidity features.",
        "Same-sample Forward-OOS improvement after freezing the feature definition.",
    ),
    ResearchHypothesis(
        "flow_toxicity_adverse_selection",
        HypothesisTier.PLAUSIBLE_BUT_UNPROVEN,
        "Aggressive flow followed by asymmetric adverse response helps distinguish informed flow from noise.",
        ("trades", "quotes/depth", "causal timestamps"),
        "Reject if response-surprise/toxicity features are redundant with existing FIA and liquidity state.",
        "Incremental paired Brier/calibration benefit on unseen data.",
    ),
    ResearchHypothesis(
        "latent_agent_mixture",
        HypothesisTier.PLAUSIBLE_BUT_UNPROVEN,
        "Observed market behaviour can be usefully represented as competition among informed, covering, liquidation, passive and noise mechanisms.",
        ("causal flow", "liquidity", "price response"),
        "Reject if mechanism weights are unstable, non-identifiable or do not improve unseen forecasts.",
        "Stable calibration plus incremental predictive information.",
    ),
    ResearchHypothesis(
        "hawkes_criticality",
        HypothesisTier.PLAUSIBLE_BUT_UNPROVEN,
        "Event self/cross-excitation and integrated-kernel spectral radius contain transition-risk information.",
        ("high-frequency event stream",),
        "Reject if fitted excitation is unstable or spectral radius adds no unseen value after volatility/liquidity controls.",
        "Frozen estimation method and Forward-OOS incremental value.",
    ),
    ResearchHypothesis(
        "information_velocity_half_life",
        HypothesisTier.ESSENTIAL,
        "Micro information should affect 4H/8H only when persistence/propagation survives across scales.",
        ("multi-scale causal series",),
        "Reject a micro feature from long-horizon use when survival is not measurable or collapses out of sample.",
        "Explicit cross-scale gate validated on untouched/forward observations.",
    ),
    ResearchHypothesis(
        "information_geometry_regime_shift",
        HypothesisTier.PLAUSIBLE_BUT_UNPROVEN,
        "Distributional geometry can detect silent state shifts not captured by point statistics.",
        ("state distributions over time",),
        "Reject if divergence measures duplicate simpler regime statistics or are unstable to binning.",
        "Robust incremental regime-detection and forecast benefit.",
    ),
    ResearchHypothesis(
        "pid_synergy_redundancy",
        HypothesisTier.PLAUSIBLE_BUT_UNPROVEN,
        "Conditional information and partial-information structure can reduce double counting across correlated evidence lanes.",
        ("sufficient joint samples",),
        "Reject approximations that are sample-unstable or materially distort calibration.",
        "Stable redundancy control and unseen calibration improvement.",
    ),
    ResearchHypothesis(
        "market_state_tension",
        HypothesisTier.SPECULATIVE,
        "A compact tension summary may capture interaction among pressure, criticality, flow, asymmetry and structural stress.",
        ("validated component estimates",),
        "Reject MST if it is redundant with its components or sensitive to arbitrary formula choices.",
        "Only promote a simpler frozen form if it adds unseen information beyond components.",
    ),
    ResearchHypothesis(
        "inverse_game_or_irl",
        HypothesisTier.SPECULATIVE,
        "Inverse decision/game formulations may recover latent urgency or inventory pressure.",
        ("rich agent-level or high-resolution behavioural data",),
        "Kill immediately if latent objectives are non-identifiable or unstable under equivalent observations.",
        "Strong identifiability evidence before any predictive test.",
    ),
    ResearchHypothesis(
        "free_energy_predictive_coding",
        HypothesisTier.SPECULATIVE,
        "Prediction-error/free-energy style summaries may compactly represent market expectation mismatch.",
        ("well-defined generative observation model",),
        "Reject if it only renames residual surprise without incremental information.",
        "MDL/complexity-adjusted unseen benefit.",
    ),
    ResearchHypothesis(
        "topological_state_features",
        HypothesisTier.SPECULATIVE,
        "Topological summaries of state trajectories may identify transition geometry.",
        ("large stable state-trajectory sample",),
        "Reject if topology is sample-fragile or adds no value over geometry/transition statistics.",
        "Independent unseen benefit after multiplicity control.",
    ),
)
