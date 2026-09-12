"""UMSE Master shadow research package.

This package is intentionally isolated from production FIA code. It provides
scientific contracts, causal event handling and non-predictive shadow primitives.
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
from .shadow_engine import InputQualityReport, assess_input_quality, build_fail_closed_snapshot

__all__ = [
    "CausalObservation",
    "DataClass",
    "EventType",
    "EventWindow",
    "HorizonEstimate",
    "InputQualityReport",
    "LatentStateVector",
    "MarketEvent",
    "MarketState",
    "Mechanism",
    "PrimitiveFeatures",
    "QualityState",
    "ShadowSnapshot",
    "ShadowStatus",
    "assess_input_quality",
    "build_fail_closed_snapshot",
    "compute_primitives",
]
