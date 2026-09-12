"""UMSE MASTER V2 FULL research package.

This package is isolated from production CLEAR NASDAQ. It may reuse repaired
UMSE V1 research contracts but must not mutate production behavior.
"""

from .contracts import (
    EvidenceStatus,
    MBOAction,
    MBORecord,
    QueueSurvivalObservation,
    QueueSurvivalReport,
    Side,
)
from .counterfactual import (
    CounterfactualDiagnostic,
    CounterfactualObservation,
    StratumEffect,
    estimate_stratified_counterfactual,
)
from .cross_scale_transport import CrossScaleTransport, TransportConfig, assess_transport
from .information_velocity import InformationVelocityReport, TimedShock, estimate_information_velocity
from .leadlag_null import LeadLagEvidence, circular_shift_leadlag_evidence
from .mechanism_competition import (
    Mechanism,
    MechanismCompetition,
    MechanismEvidence,
    compete_mechanisms,
)
from .model_competition import ComplexityCompetition, compare_predictive_complexity
from .orderbook_memory import OrderBookMemory, estimate_orderbook_memory
from .paired_validation import (
    PRIMARY_HORIZON,
    Horizon,
    V2HorizonValidation,
    V2PairedForecastRecord,
    V2ValidationPlan,
    V2ValidationSuite,
    evaluate_v2_horizon,
    evaluate_v2_suite,
)
from .pipeline import V2PipelineConfig, V2ShadowDiagnostics, run_v2_shadow
from .queue_hazard import QueueLifetimeDiagnostics, SurvivalPoint, kaplan_meier_queue_lifetime
from .queue_survival import reconstruct_queue_survival
from .resistance_field import ResistanceConfig, ResistanceField, estimate_resistance_field
from .topology_regime import StatePoint, TopologicalRegimeSignature, topological_regime_signature

__all__ = [
    "EvidenceStatus",
    "MBOAction",
    "MBORecord",
    "QueueSurvivalObservation",
    "QueueSurvivalReport",
    "Side",
    "TimedShock",
    "InformationVelocityReport",
    "estimate_information_velocity",
    "LeadLagEvidence",
    "circular_shift_leadlag_evidence",
    "OrderBookMemory",
    "estimate_orderbook_memory",
    "reconstruct_queue_survival",
    "QueueLifetimeDiagnostics",
    "SurvivalPoint",
    "kaplan_meier_queue_lifetime",
    "ResistanceConfig",
    "ResistanceField",
    "estimate_resistance_field",
    "TransportConfig",
    "CrossScaleTransport",
    "assess_transport",
    "ComplexityCompetition",
    "compare_predictive_complexity",
    "Mechanism",
    "MechanismEvidence",
    "MechanismCompetition",
    "compete_mechanisms",
    "CounterfactualObservation",
    "StratumEffect",
    "CounterfactualDiagnostic",
    "estimate_stratified_counterfactual",
    "StatePoint",
    "TopologicalRegimeSignature",
    "topological_regime_signature",
    "Horizon",
    "PRIMARY_HORIZON",
    "V2ValidationPlan",
    "V2PairedForecastRecord",
    "V2HorizonValidation",
    "V2ValidationSuite",
    "evaluate_v2_horizon",
    "evaluate_v2_suite",
    "V2PipelineConfig",
    "V2ShadowDiagnostics",
    "run_v2_shadow",
]
