"""CNMI shadow research-governance adapter.

This module is intentionally non-authoritative and non-production. It translates
selected frozen CNMI research-governance rules into a fail-closed executable
adapter without modifying the frozen CNMI artifacts or CLEAR NASDAQ forecast
logic.

Identity: CNMI_SHADOW_ADAPTER_V1_NONAUTHORITATIVE
Production influence: none
Deployment authority: none
Predictive edge claim: none

The frozen CNMI package explicitly stopped before implementation/integration.
This adapter therefore does NOT claim to be the frozen CNMI package itself. It
is a separate shadow implementation created under later user authorization.
Protocol-specific margins, statistical procedures and preference maps must be
supplied by the calling protocol; this module invents no universal defaults.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

ADAPTER_ID = "CNMI_SHADOW_ADAPTER_V1_NONAUTHORITATIVE"
FRAMEWORK_SCOPE = "RESEARCH_GOVERNANCE_ONLY"
PRODUCTION_INFLUENCE = False
DEPLOYMENT_AUTHORIZED = False
PREDICTIVE_EDGE_CLAIMED = False
CNMI_NATIVE_105_34_10 = "NOT_CLAIMED"

LEVELS = ("RESEARCH", "CORE", "PRODUCTION")

CLAIM_TYPES = {
    "EMPIRICAL_SUPERIORITY",
    "EMPIRICAL_NONINFERIORITY",
    "EMPIRICAL_EQUIVALENCE",
    "IDENTIFICATION_RESULT",
    "IMPOSSIBILITY_THEOREM",
    "RESOURCE_SAVING_THEOREM",
    "FORMAL_EQUIVALENCE_RESULT",
    "ROBUSTNESS_RESULT",
    "FALSIFICATION_METHOD_RESULT",
}

HARD_GATES = {
    "H1": "Time / future integrity",
    "H2": "Outcome contamination control",
    "H3": "Protected artifact immutability",
    "H4": "Data legality/provenance",
    "H5": "Protocol identity",
    "H6": "Resource feasibility",
    "H7": "Reproducibility",
    "H8": "Security/integrity",
    "H9": "Statistical/formal validity",
}

COMPLETENESS_STATES = {
    "COMPLETE_VERIFIED",
    "COMPLETE_BY_CONTROLLED_ACCESS_BOUNDARY",
    "INCOMPLETE_KNOWN",
    "HISTORICALLY_UNRECOVERABLE",
    "RECOVERABLE_BUT_MISSING",
    "DELIBERATELY_UNDOCUMENTED_OR_DESTROYED",
    "LATENT_PRIOR_EXPOSURE_NOT_EXCLUDABLE",
}

UNTOUCHED_ELIGIBLE_STATES = {
    "COMPLETE_VERIFIED",
    "COMPLETE_BY_CONTROLLED_ACCESS_BOUNDARY",
}

PARETO_STATES = {
    "POINT_ESTIMATE_PARETO",
    "CONFIRMATORY_PARETO_ESTABLISHED",
    "PARETO_DOMINANCE_NOT_IDENTIFIED",
    "PARETO_INCOMPARABLE",
}

INTEGRITY_FAILURE_STATES = {"DELIBERATELY_UNDOCUMENTED_OR_DESTROYED"}
RECOVERABLE_PENDING_STATES = {"RECOVERABLE_BUT_MISSING"}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _flag(record: Mapping[str, Any], name: str) -> bool:
    return record.get(name) is True


def _require(record: Mapping[str, Any], names: Iterable[str], reasons: List[str], prefix: str) -> bool:
    ok = True
    for name in names:
        if record.get(name) is not True:
            reasons.append(f"{prefix}:{name}=MISSING_OR_FALSE")
            ok = False
    return ok


def status() -> Dict[str, Any]:
    return {
        "adapter_id": ADAPTER_ID,
        "framework_scope": FRAMEWORK_SCOPE,
        "authoritative_cnmi_implementation": False,
        "production_influence": PRODUCTION_INFLUENCE,
        "deployment_authorized": DEPLOYMENT_AUTHORIZED,
        "predictive_edge_claimed": PREDICTIVE_EDGE_CLAIMED,
        "cnmi_native_105_34_10": CNMI_NATIVE_105_34_10,
        "hard_gates": dict(HARD_GATES),
        "levels": list(LEVELS),
        "policy": {
            "hard_failures_non_compensable": True,
            "universal_materiality_margin": None,
            "universal_statistical_pareto_test": None,
            "universal_scalar_preference_map": None,
            "production_admission_implies_deployment": False,
        },
    }


def _evaluate_hard_gates(candidate: Mapping[str, Any], requested_level: str, reasons: List[str]) -> bool:
    provided = candidate.get("hard_gates")
    applicable = candidate.get("applicable_hard_gates")
    if not isinstance(provided, Mapping):
        reasons.append("HARD_GATES:MISSING")
        return False
    if not isinstance(applicable, list) or not applicable:
        reasons.append("APPLICABLE_HARD_GATES:MISSING")
        return False

    ok = True
    for gate in applicable:
        if gate not in HARD_GATES:
            reasons.append(f"HARD_GATE:{gate}=UNKNOWN")
            ok = False
            continue
        # Fail closed: missing/None is a failed gate, not an implicit pass.
        if provided.get(gate) is not True:
            reasons.append(f"HARD_GATE:{gate}=FAILED_OR_UNPROVEN")
            ok = False

    # Requested level is carried only for auditability. No lower-level success
    # can compensate for a failed applicable hard gate at the requested level.
    if not ok:
        reasons.append(f"REQUESTED_LEVEL:{requested_level}=REJECTED_HARD_GATE")
    return ok


def _evaluate_claims(candidate: Mapping[str, Any], reasons: List[str]) -> bool:
    claims = candidate.get("claims")
    if not isinstance(claims, list) or not claims:
        reasons.append("CLAIMS:MISSING")
        return False
    ok = True
    for i, claim in enumerate(claims):
        if not isinstance(claim, Mapping):
            reasons.append(f"CLAIM:{i}=MALFORMED")
            ok = False
            continue
        ctype = str(claim.get("type") or "").upper()
        if ctype not in CLAIM_TYPES:
            if not claim.get("explicit_evidence_rule"):
                reasons.append(f"CLAIM:{i}=UNKNOWN_TYPE_WITHOUT_EVIDENCE_RULE")
                ok = False
        if claim.get("requires_materiality") is True:
            identity = claim.get("materiality_identity")
            if not isinstance(identity, Mapping):
                reasons.append(f"CLAIM:{i}=MATERIALITY_IDENTITY_MISSING")
                ok = False
            else:
                required = {
                    "estimand", "target_population", "eligibility_rule", "outcome_transform",
                    "horizon", "aggregation_rule", "canonical_units", "margin",
                    "provenance_class", "provenance_evidence", "freeze_identity",
                    "permitted_claim_semantics",
                }
                missing = sorted(required - set(identity))
                if missing:
                    reasons.append(f"CLAIM:{i}=MATERIALITY_IDENTITY_INCOMPLETE:{','.join(missing)}")
                    ok = False
                if identity.get("confirmatory_outcome_used_to_set_margin") is True:
                    reasons.append(f"CLAIM:{i}=MATERIALITY_CONTAMINATED")
                    ok = False
        if claim.get("requires_confirmatory_pareto") is True:
            state = str(claim.get("pareto_state") or "")
            if state not in PARETO_STATES:
                reasons.append(f"CLAIM:{i}=PARETO_STATE_MISSING")
                ok = False
            elif state != "CONFIRMATORY_PARETO_ESTABLISHED":
                reasons.append(f"CLAIM:{i}=CONFIRMATORY_PARETO_NOT_ESTABLISHED")
                ok = False
    return ok


def _research_requirements(candidate: Mapping[str, Any], reasons: List[str]) -> bool:
    return _require(
        candidate,
        (
            "research_question_discriminating",
            "decision_relevant_test_or_proof_exists",
            "research_resource_ceiling_declared",
            "stop_or_falsification_condition_declared",
            "not_represented_as_predictive_edge",
        ),
        reasons,
        "RESEARCH",
    )


def _core_requirements(candidate: Mapping[str, Any], reasons: List[str]) -> bool:
    ok = _require(
        candidate,
        (
            "definitions_explicit",
            "assumptions_explicit",
            "logic_internally_consistent",
            "known_counterexamples_addressed",
            "claim_relevant_tests_present",
            "identifiability_status_declared",
            "evidence_vs_assumption_attribution_declared",
            "system_component_attribution_declared",
            "adaptive_search_and_metric_selection_disclosed",
            "typed_proof_or_evidence_status_declared",
        ),
        reasons,
        "CORE",
    )
    if candidate.get("unresolved_critical_counterexample") is True:
        reasons.append("CORE:UNRESOLVED_CRITICAL_COUNTEREXAMPLE")
        ok = False
    return ok


def _production_requirements(candidate: Mapping[str, Any], reasons: List[str]) -> bool:
    ok = _require(
        candidate,
        (
            "prospective_evaluation",
            "frozen_protocol_identity",
            "fair_comparison_contract_satisfied",
            "claim_specific_criterion_satisfied",
            "meta_selection_multiplicity_adaptivity_control_valid",
            "coverage_abstention_treatment_valid",
            "production_resources_declared_feasible",
            "provenance_security_integrity_reproducibility_pass",
            "protected_artifacts_unchanged",
            "prospective_evidence_independence_sufficient",
        ),
        reasons,
        "PRODUCTION",
    )

    completeness = str(candidate.get("provenance_completeness_state") or "")
    if completeness not in COMPLETENESS_STATES:
        reasons.append("PRODUCTION:PROVENANCE_COMPLETENESS_STATE_MISSING")
        ok = False
    elif completeness in INTEGRITY_FAILURE_STATES:
        reasons.append("INTEGRITY_FAILURE:DELIBERATE_PROVENANCE_LOSS")
        ok = False
    elif completeness in RECOVERABLE_PENDING_STATES:
        reasons.append("RECOVERABLE_BUT_MISSING:PROVENANCE_PENDING")
        ok = False

    if candidate.get("claims_untouched_confirmation") is True:
        if completeness not in UNTOUCHED_ELIGIBLE_STATES:
            reasons.append("PRODUCTION:UNTOUCHED_STATUS_UNAVAILABLE")
            ok = False
        if candidate.get("affirmative_access_provenance_argument") is not True:
            reasons.append("PRODUCTION:AFFIRMATIVE_ACCESS_PROVENANCE_ARGUMENT_MISSING")
            ok = False
        if candidate.get("material_prior_exposure_excluded") is not True:
            reasons.append("PRODUCTION:LATENT_PRIOR_EXPOSURE_NOT_EXCLUDABLE")
            ok = False

    return ok


def evaluate_candidate(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate a candidate under the shadow governance adapter.

    The caller supplies protocol-specific margins and inference results. This
    function validates governance structure; it does not invent scientific
    thresholds, statistical corrections, Pareto tests or utility weights.
    """
    if not isinstance(candidate, Mapping):
        return {
            **status(),
            "ok": False,
            "decision": "ABSTAIN_MALFORMED_CANDIDATE",
            "research_admissible": False,
            "core_admissible": False,
            "production_admissible": False,
            "deployment_authorized": False,
            "reasons": ["CANDIDATE:MALFORMED"],
        }

    requested = str(candidate.get("requested_level") or "").upper()
    reasons: List[str] = []
    if requested not in LEVELS:
        reasons.append("REQUESTED_LEVEL:INVALID_OR_MISSING")

    hard_ok = _evaluate_hard_gates(candidate, requested or "UNKNOWN", reasons)
    claims_ok = _evaluate_claims(candidate, reasons)

    research_ok = hard_ok and claims_ok and _research_requirements(candidate, reasons)
    core_ok = research_ok and _core_requirements(candidate, reasons)
    production_ok = core_ok and _production_requirements(candidate, reasons)

    # Admission is hierarchical and never auto-promotes beyond what was asked.
    earned = "NONE"
    if research_ok:
        earned = "RESEARCH"
    if core_ok:
        earned = "CORE"
    if production_ok:
        earned = "PRODUCTION"

    requested_supported = {
        "RESEARCH": research_ok,
        "CORE": core_ok,
        "PRODUCTION": production_ok,
    }.get(requested, False)

    decision = f"{requested}_ADMISSIBLE" if requested_supported else f"{requested or 'UNKNOWN'}_NOT_ADMISSIBLE"

    result = {
        **status(),
        "ok": True,
        "decision": decision,
        "requested_level": requested or None,
        "highest_earned_level": earned,
        "research_admissible": research_ok,
        "core_admissible": core_ok,
        "production_admissible": production_ok,
        "deployment_authorized": False,
        "production_influence": False,
        "reasons": reasons,
        "positive_metrics_can_override_hard_gate": False,
        "candidate_digest": _digest(candidate),
    }
    result["result_digest"] = _digest(result)
    return result
