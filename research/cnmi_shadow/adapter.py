"""CNMI shadow research-governance adapter.

This module is intentionally non-authoritative and non-production. It translates
selected frozen CNMI research-governance rules into a fail-closed executable
adapter without modifying the frozen CNMI artifacts or CLEAR NASDAQ forecast
logic.

Identity: CNMI_SHADOW_ADAPTER_V1_1_NONAUTHORITATIVE
Production influence: none
Deployment authority: none
Predictive edge claim: none

Hardening note:
A prior version could report ``production_admissible=True`` from caller-supplied
booleans alone. That overstated what a non-authoritative shadow adapter can
prove. V1.1 therefore separates *structural production eligibility* from
*production admission*. Structural eligibility may be evaluated here, but
production admission remains false until a trusted external verifier is bound
and executed. This adapter never converts self-attestation into production
proof.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

ADAPTER_ID = "CNMI_SHADOW_ADAPTER_V1_1_NONAUTHORITATIVE"
FRAMEWORK_SCOPE = "RESEARCH_GOVERNANCE_ONLY"
PRODUCTION_INFLUENCE = False
DEPLOYMENT_AUTHORIZED = False
PREDICTIVE_EDGE_CLAIMED = False
CNMI_NATIVE_105_34_10 = "NOT_CLAIMED"
EXTERNAL_PRODUCTION_VERIFIER_BOUND = False

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
REQUIRED_PRODUCTION_HARD_GATES = frozenset(HARD_GATES)

COMPLETENESS_STATES = {
    "COMPLETE_VERIFIED",
    "COMPLETE_BY_CONTROLLED_ACCESS_BOUNDARY",
    "INCOMPLETE_KNOWN",
    "HISTORICALLY_UNRECOVERABLE",
    "RECOVERABLE_BUT_MISSING",
    "DELIBERATELY_UNDOCUMENTED_OR_DESTROYED",
    "LATENT_PRIOR_EXPOSURE_NOT_EXCLUDABLE",
}

PRODUCTION_ALLOWED_PROVENANCE_STATES = {
    "COMPLETE_VERIFIED",
    "COMPLETE_BY_CONTROLLED_ACCESS_BOUNDARY",
}
UNTOUCHED_ELIGIBLE_STATES = set(PRODUCTION_ALLOWED_PROVENANCE_STATES)

PARETO_STATES = {
    "POINT_ESTIMATE_PARETO",
    "CONFIRMATORY_PARETO_ESTABLISHED",
    "PARETO_DOMINANCE_NOT_IDENTIFIED",
    "PARETO_INCOMPARABLE",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


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
        "external_production_verifier_bound": EXTERNAL_PRODUCTION_VERIFIER_BOUND,
        "hard_gates": dict(HARD_GATES),
        "levels": list(LEVELS),
        "policy": {
            "hard_failures_non_compensable": True,
            "universal_materiality_margin": None,
            "universal_statistical_pareto_test": None,
            "universal_scalar_preference_map": None,
            "production_admission_implies_deployment": False,
            "production_requires_all_hard_gates": True,
            "unknown_claim_types_fail_closed": True,
            "incomplete_provenance_blocks_production": True,
            "bare_candidate_self_attestation_never_enough": True,
            "production_requires_external_verifier": True,
            "requested_level_caps_evaluation_scope": True,
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
    normalized = [str(g) for g in applicable]
    if len(normalized) != len(set(normalized)):
        reasons.append("APPLICABLE_HARD_GATES:DUPLICATE")
        ok = False

    unknown = sorted(set(normalized) - set(HARD_GATES))
    for gate in unknown:
        reasons.append(f"HARD_GATE:{gate}=UNKNOWN")
        ok = False

    # Production is not allowed to let the caller silently omit a hard gate.
    gates_to_check = set(normalized)
    if requested_level == "PRODUCTION":
        missing = sorted(REQUIRED_PRODUCTION_HARD_GATES - set(normalized))
        if missing:
            reasons.append(f"PRODUCTION:HARD_GATES_NOT_DECLARED:{','.join(missing)}")
            ok = False
        gates_to_check |= REQUIRED_PRODUCTION_HARD_GATES

    for gate in sorted(gates_to_check):
        if gate not in HARD_GATES:
            continue
        if provided.get(gate) is not True:
            reasons.append(f"HARD_GATE:{gate}=FAILED_OR_UNPROVEN")
            ok = False

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
            reasons.append(f"CLAIM:{i}=UNKNOWN_TYPE_UNREGISTERED")
            ok = False

        if claim.get("requires_materiality") is True:
            identity = claim.get("materiality_identity")
            if not isinstance(identity, Mapping):
                reasons.append(f"CLAIM:{i}=MATERIALITY_IDENTITY_MISSING")
                ok = False
            else:
                required = {
                    "estimand",
                    "target_population",
                    "eligibility_rule",
                    "outcome_transform",
                    "horizon",
                    "aggregation_rule",
                    "canonical_units",
                    "margin",
                    "provenance_class",
                    "provenance_evidence",
                    "freeze_identity",
                    "permitted_claim_semantics",
                }
                missing = sorted(required - set(identity))
                if missing:
                    reasons.append(f"CLAIM:{i}=MATERIALITY_IDENTITY_INCOMPLETE:{','.join(missing)}")
                    ok = False

                empty = sorted(
                    name
                    for name in required & set(identity)
                    if identity.get(name) is None
                    or (isinstance(identity.get(name), str) and not identity.get(name).strip())
                )
                if empty:
                    reasons.append(f"CLAIM:{i}=MATERIALITY_IDENTITY_EMPTY:{','.join(empty)}")
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
    """Return structural eligibility only, never final production admission."""
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
    elif completeness not in PRODUCTION_ALLOWED_PROVENANCE_STATES:
        reasons.append(f"PRODUCTION:PROVENANCE_NOT_COMPLETE:{completeness}")
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
    function validates governance structure; it does not independently verify
    market data, ledgers, artifacts, independence, signatures, or external
    runtime evidence. Therefore a structurally complete production candidate is
    reported only as ``production_structurally_eligible``. Final production
    admission remains false until a trusted external verifier is actually bound.
    """
    if not isinstance(candidate, Mapping):
        return {
            **status(),
            "ok": False,
            "decision": "ABSTAIN_MALFORMED_CANDIDATE",
            "research_admissible": False,
            "core_admissible": False,
            "production_structurally_eligible": False,
            "production_admissible": False,
            "deployment_authorized": False,
            "evidence_independence_status": "NOT_EVALUATED",
            "reasons": ["CANDIDATE:MALFORMED"],
        }

    requested = str(candidate.get("requested_level") or "").upper()
    reasons: List[str] = []
    requested_valid = requested in LEVELS
    if not requested_valid:
        reasons.append("REQUESTED_LEVEL:INVALID_OR_MISSING")

    hard_ok = _evaluate_hard_gates(candidate, requested or "UNKNOWN", reasons)
    claims_ok = _evaluate_claims(candidate, reasons)

    # A candidate may only earn the level it asked us to adjudicate (plus the
    # prerequisites below it). This prevents a RESEARCH/invalid request from
    # accidentally surfacing a production-eligibility flag that never received
    # production-level hard-gate adjudication.
    research_ok = requested_valid and hard_ok and claims_ok and _research_requirements(candidate, reasons)
    core_ok = (
        requested in {"CORE", "PRODUCTION"}
        and research_ok
        and _core_requirements(candidate, reasons)
    )
    production_structural_ok = (
        requested == "PRODUCTION"
        and core_ok
        and _production_requirements(candidate, reasons)
    )

    # This module is deliberately not a trusted external verifier. No combination
    # of caller-supplied booleans can turn that fact into a production proof.
    production_ok = False
    if requested == "PRODUCTION" and production_structural_ok:
        reasons.append("PRODUCTION:EXTERNAL_VERIFIER_NOT_BOUND")

    earned = "NONE"
    if research_ok:
        earned = "RESEARCH"
    if core_ok:
        earned = "CORE"

    structural_earned = earned
    if production_structural_ok:
        structural_earned = "PRODUCTION"

    requested_supported = {
        "RESEARCH": research_ok,
        "CORE": core_ok,
        "PRODUCTION": production_ok,
    }.get(requested, False)

    decision = (
        f"{requested}_ADMISSIBLE"
        if requested_supported
        else f"{requested or 'UNKNOWN'}_NOT_ADMISSIBLE"
    )

    result = {
        **status(),
        "ok": True,
        "decision": decision,
        "requested_level": requested or None,
        "highest_earned_level": earned,
        "highest_structural_level": structural_earned,
        "research_admissible": research_ok,
        "core_admissible": core_ok,
        "production_structurally_eligible": production_structural_ok,
        "production_admissible": production_ok,
        "deployment_authorized": False,
        "production_influence": False,
        "evidence_independence_status": (
            "DEPENDENCE_NOT_EXCLUDABLE"
            if production_structural_ok
            else "NOT_ESTABLISHED"
        ),
        "reasons": reasons,
        "positive_metrics_can_override_hard_gate": False,
        "candidate_digest": _digest(candidate),
    }
    result["result_digest"] = _digest(result)
    return result
