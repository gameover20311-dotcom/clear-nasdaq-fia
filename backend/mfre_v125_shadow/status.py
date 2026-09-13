from __future__ import annotations

"""Machine-readable truth surface for MFRE shadow integration.

This module is deliberately pure/read-only.  It exposes integration truth for a
future dashboard panel without creating market authority or mutating FIA state.
"""

from typing import Any, Mapping

from .adapters import MFREInputFrame
from .contract import (
    IMPLEMENTATION_SCOPE,
    INTEGRATION_BINDING_HASH,
    MFRE_INCREMENTAL_VALUE,
    MFRE_VERSION,
    NOVEL_MATHEMATICS,
    PRODUCTION_AUTHORIZED,
    REAL_MARKET_EDGE,
)
from .controller import MFREShadowController, ShadowRunStatus
from .types import DeclarationBundle

STATUS_SCHEMA = "clear-nasdaq-mfre-shadow-status/v1"
THEORY_FREEZE = "FINAL_FREEZE_PASS"
PREDICTIVE_EDGE = "NOT_PROVEN"
INTEGRATION_PHASE = "PHASE_4_TRUTH_STATUS_SURFACE"

# This is intentionally not caller-configurable.  It becomes True only in a
# future code change that lands a separately audited execution engine.
EXECUTION_ENGINE_BOUND = False


def _declaration_status(declarations: DeclarationBundle | None) -> str:
    if declarations is None:
        return "MISSING"
    if not declarations.scientifically_frozen:
        return "UNFROZEN"
    return "FROZEN"


def build_truth_status(
    frame: MFREInputFrame,
    declarations: DeclarationBundle | None = None,
) -> Mapping[str, Any]:
    """Return the single fail-closed status object a dashboard may render.

    `dashboard_decision_ready` is intentionally false in this integration
    phase.  Even a fully frozen declaration bundle can only reach
    READY_SHADOW_CONTRACT_ONLY until a separately audited MFRE execution engine
    exists; production authority is explicitly forbidden by the frozen theory
    contract.
    """

    result = MFREShadowController(declarations).assess(frame)
    research_blockers = list(result.reasons)
    if not EXECUTION_ENGINE_BOUND and "MFRE_EXECUTION_ENGINE_NOT_YET_BOUND" not in research_blockers:
        research_blockers.append("MFRE_EXECUTION_ENGINE_NOT_YET_BOUND")

    shadow_contract_ready = result.status is ShadowRunStatus.READY_SHADOW_CONTRACT_ONLY
    shadow_runtime_ready = shadow_contract_ready and EXECUTION_ENGINE_BOUND

    decision_blockers = list(research_blockers)
    for blocker in ("MFRE_PRODUCTION_AUTHORITY_NOT_GRANTED", "PREDICTIVE_EDGE_NOT_PROVEN"):
        if blocker not in decision_blockers:
            decision_blockers.append(blocker)

    return {
        "schema": STATUS_SCHEMA,
        "integration_phase": INTEGRATION_PHASE,
        "mfre_version": MFRE_VERSION,
        "theory_freeze": THEORY_FREEZE,
        "implementation_scope": IMPLEMENTATION_SCOPE,
        "production_authorized": PRODUCTION_AUTHORIZED,
        "decision_authority": "NONE",
        "predictive_edge": PREDICTIVE_EDGE,
        "real_market_edge": REAL_MARKET_EDGE,
        "mfre_incremental_value": MFRE_INCREMENTAL_VALUE,
        "novel_mathematics": NOVEL_MATHEMATICS,
        "integration_binding_hash": INTEGRATION_BINDING_HASH,
        "declaration_status": _declaration_status(declarations),
        "protocol_identity": result.protocol_identity,
        "run_status": result.status.value,
        "execution_engine_bound": EXECUTION_ENGINE_BOUND,
        "shadow_contract_ready": shadow_contract_ready,
        "shadow_runtime_ready": shadow_runtime_ready,
        "dashboard_status_surface_ready": True,
        "dashboard_decision_ready": False,
        "directional_override": None,
        "shadow_lab": {
            "available": frame.shadow.available,
            "hypothesis_count": len(frame.shadow.hypotheses),
            "scientific_status": frame.shadow.note or "UNKNOWN",
            "source_digest": frame.shadow.source_digest,
        },
        "umse": {
            "available": frame.umse.available,
            "integrity_pass": frame.umse.integrity_pass,
            "state_label": frame.umse.state_label,
            "scientific_status": frame.umse.note or "UNKNOWN",
            "source_digest": frame.umse.source_digest,
        },
        "dpcse": {
            "status": frame.dpcse.status,
            "candidate_model_frozen": frame.dpcse.candidate_model_frozen,
            "decision": frame.dpcse.decision,
            "p_bull": frame.dpcse.p_bull,
            "p_bear": frame.dpcse.p_bear,
            "locked_rows": frame.dpcse.locked_rows,
            "predictive_edge": frame.dpcse.predictive_edge,
            "source_digest": frame.dpcse.source_digest,
        },
        "research_blockers": tuple(research_blockers),
        "decision_blockers": tuple(decision_blockers),
    }
