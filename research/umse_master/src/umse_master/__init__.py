"""UMSE Master shadow research package.

This package is intentionally isolated from production FIA code. It provides
Phase-0 scientific contracts and fail-closed scaffolding only.
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
from .shadow_engine import InputQualityReport, assess_input_quality, build_fail_closed_snapshot

__all__ = [
    "CausalObservation",
    "DataClass",
    "HorizonEstimate",
    "InputQualityReport",
    "LatentStateVector",
    "MarketState",
    "Mechanism",
    "QualityState",
    "ShadowSnapshot",
    "ShadowStatus",
    "assess_input_quality",
    "build_fail_closed_snapshot",
]
