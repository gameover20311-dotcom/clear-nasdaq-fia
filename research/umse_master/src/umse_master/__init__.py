"""UMSE Master shadow research package.

Research-only causal market-state engine. Nothing in this package is allowed to
affect BASE_FIA without a separately frozen, audited and unseen-data promotion path.
"""

from .contracts import CausalObservation, DataClass, HorizonEstimate, LatentStateVector, MarketState, Mechanism, QualityState, ShadowSnapshot, ShadowStatus
from .events import EventType, EventWindow, MarketEvent
from .primitives import PrimitiveFeatures, compute_primitives
from .liquidity import BookLevel, LiquidityField, OrderBookSnapshot, estimate_liquidity_field
from .impact import ImpactContext, ImpactDecay, ImpactModelConfig, ResponseSurprise, compute_response_surprise, estimate_impact_decay, expected_price_impact
from .hawkes import HawkesDiagnostics, HawkesNetworkConfig, hawkes_diagnostics
from .information import InformationEdge, PIDApproximation, build_information_edge, conditional_mutual_information, entropy, mutual_information, pid_i_min_approximation, transfer_entropy
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
from .agents import AgentPressureInference, infer_agent_pressure
from .survival import StateSurvivalDiagnostics, SurvivalPoint, analyze_state_survival, kaplan_meier
from .state_space import FilterStep, HMMFilterResult, forward_filter
from .irreversibility import IrreversibilityDiagnostics, path_irreversibility
from .marginal_info import MarginalInformationResult, incremental_information, shapley_information
from .complexity import ComplexityAssessment, assess_complexity
from .hypotheses import HypothesisTier, ResearchHypothesis, MASTER_HYPOTHESES

__all__ = [name for name in globals() if not name.startswith("_")]
