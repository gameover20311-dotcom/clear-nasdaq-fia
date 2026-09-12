"""UMSE Master shadow research package.

This package is intentionally isolated from production FIA code. It contains
scientific contracts, causal market-state primitives, validation utilities and
shadow-only research orchestration. Nothing here is allowed to affect BASE_FIA
without a separately frozen and validated promotion path.
"""

from .contracts import (
    CausalObservation,
    DataClass,
    HorizonEstimate,
    LatentStateVector,
    MarketState,
    Mechanism,
    QualityState,
    ShadowSnapshot,
    ShadowStatus,
)
from .events import EventType, EventWindow, MarketEvent
from .primitives import PrimitiveFeatures, compute_primitives
from .liquidity import BookLevel, LiquidityField, OrderBookSnapshot, estimate_liquidity_field
from .impact import (
    ImpactContext,
    ImpactDecay,
    ImpactModelConfig,
    ResponseSurprise,
    compute_response_surprise,
    estimate_impact_decay,
    expected_price_impact,
)
from .hawkes import HawkesDiagnostics, HawkesNetworkConfig, hawkes_diagnostics
from .information import (
    InformationEdge,
    PIDApproximation,
    build_information_edge,
    conditional_mutual_information,
    entropy,
    mutual_information,
    pid_i_min_approximation,
    transfer_entropy,
)
from .geometry import GeometryShift, distribution_shift
from .mechanisms import MechanismCompetition, MechanismEvidence, compete_mechanisms
from .state import StateEvidence, StateInference, infer_state
from .cross_scale import CrossScaleReport, Scale, ScaleEvidence, assess_cross_scale, estimate_half_life
from .criticality import CriticalityDiagnostics, compute_criticality
from .mst import MSTComponents, MSTResult, compute_mst
from .fusion import ExpertOpinion, FusionResult, reliability_weighted_fusion
from .validation import PairedValidationResult, evaluate_paired_candidate, multiclass_brier
from .replay import CausalReplay, ReplayClass, ReplayDecision
from .adapters import AdapterDeclaration, Capability, InMemoryAdapter, MarketDataAdapter
from .pipeline import UMSEResearchDiagnostics, UMSEShadowRun, run_umse_shadow
from .shadow_engine import InputQualityReport, assess_input_quality, build_fail_closed_snapshot

__all__ = [
    "AdapterDeclaration", "BookLevel", "Capability", "CausalObservation", "CausalReplay",
    "CriticalityDiagnostics", "CrossScaleReport", "DataClass", "EventType", "EventWindow",
    "ExpertOpinion", "FusionResult", "GeometryShift", "HawkesDiagnostics", "HawkesNetworkConfig",
    "HorizonEstimate", "ImpactContext", "ImpactDecay", "ImpactModelConfig", "InMemoryAdapter",
    "InformationEdge", "InputQualityReport", "LatentStateVector", "LiquidityField", "MarketDataAdapter",
    "MarketEvent", "MarketState", "Mechanism", "MechanismCompetition", "MechanismEvidence", "MSTComponents",
    "MSTResult", "OrderBookSnapshot", "PIDApproximation", "PairedValidationResult", "PrimitiveFeatures",
    "QualityState", "ReplayClass", "ReplayDecision", "ResponseSurprise", "Scale", "ScaleEvidence",
    "ShadowSnapshot", "ShadowStatus", "StateEvidence", "StateInference", "UMSEResearchDiagnostics",
    "UMSEShadowRun", "assess_cross_scale", "assess_input_quality", "build_fail_closed_snapshot",
    "build_information_edge", "compete_mechanisms", "compute_criticality", "compute_mst", "compute_primitives",
    "compute_response_surprise", "conditional_mutual_information", "distribution_shift", "entropy",
    "estimate_half_life", "estimate_impact_decay", "estimate_liquidity_field", "evaluate_paired_candidate",
    "expected_price_impact", "hawkes_diagnostics", "infer_state", "multiclass_brier", "mutual_information",
    "pid_i_min_approximation", "reliability_weighted_fusion", "run_umse_shadow", "transfer_entropy",
]
