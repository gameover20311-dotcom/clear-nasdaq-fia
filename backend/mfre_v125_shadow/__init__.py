"""MFRE V1.2.5 research/shadow integration kernel.

This package is deliberately outside backend/fia so it cannot silently enter
BASE_FIA scientific identity. It is not production-authorized.
"""
from .contract import (
    MFRE_VERSION, IMPLEMENTATION_SCOPE, REAL_MARKET_EDGE,
    MFRE_INCREMENTAL_VALUE, NOVEL_MATHEMATICS, PRODUCTION_AUTHORIZED,
    INTEGRATION_BINDING_HASH,
)
from .controller import MFREShadowController, ShadowRunStatus, ShadowRunResult
from .types import ActionKind, RandomnessOwnership, PrimitiveSpec, DeclarationBundle, ControlState
from .adapters import ShadowHypothesisView, UMSEView, DPCSEView, MFREInputFrame
from .upstream import (
    UPSTREAM_PROVENANCE, shadow_view_from_report,
    umse_view_from_v2_diagnostics, dpcse_view_from_bootstrap,
)

__all__ = [
    "MFRE_VERSION","IMPLEMENTATION_SCOPE","REAL_MARKET_EDGE",
    "MFRE_INCREMENTAL_VALUE","NOVEL_MATHEMATICS","PRODUCTION_AUTHORIZED",
    "INTEGRATION_BINDING_HASH","MFREShadowController","ShadowRunStatus",
    "ShadowRunResult","ActionKind","RandomnessOwnership","PrimitiveSpec",
    "DeclarationBundle","ControlState","ShadowHypothesisView","UMSEView",
    "DPCSEView","MFREInputFrame","UPSTREAM_PROVENANCE",
    "shadow_view_from_report","umse_view_from_v2_diagnostics",
    "dpcse_view_from_bootstrap",
]
