import copy
import unittest

from fia.cnmi_shadow import (
    ADAPTER_ID,
    CNMI_NATIVE_105_34_10,
    HARD_GATES,
    evaluate_candidate,
    status,
)


def base_candidate(level="PRODUCTION"):
    c = {
        "requested_level": level,
        "applicable_hard_gates": list(HARD_GATES),
        "hard_gates": {gate: True for gate in HARD_GATES},
        "claims": [{"type": "ROBUSTNESS_RESULT"}],
        "research_question_discriminating": True,
        "decision_relevant_test_or_proof_exists": True,
        "research_resource_ceiling_declared": True,
        "stop_or_falsification_condition_declared": True,
        "not_represented_as_predictive_edge": True,
        "definitions_explicit": True,
        "assumptions_explicit": True,
        "logic_internally_consistent": True,
        "known_counterexamples_addressed": True,
        "claim_relevant_tests_present": True,
        "identifiability_status_declared": True,
        "evidence_vs_assumption_attribution_declared": True,
        "system_component_attribution_declared": True,
        "adaptive_search_and_metric_selection_disclosed": True,
        "typed_proof_or_evidence_status_declared": True,
        "unresolved_critical_counterexample": False,
        "prospective_evaluation": True,
        "frozen_protocol_identity": True,
        "fair_comparison_contract_satisfied": True,
        "claim_specific_criterion_satisfied": True,
        "meta_selection_multiplicity_adaptivity_control_valid": True,
        "coverage_abstention_treatment_valid": True,
        "production_resources_declared_feasible": True,
        "provenance_security_integrity_reproducibility_pass": True,
        "protected_artifacts_unchanged": True,
        "prospective_evidence_independence_sufficient": True,
        "provenance_completeness_state": "COMPLETE_VERIFIED",
        "claims_untouched_confirmation": False,
    }
    return c


class CNMIShadowTests(unittest.TestCase):
    def test_identity_is_explicitly_nonauthoritative(self):
        s = status()
        self.assertEqual(s["adapter_id"], ADAPTER_ID)
        self.assertFalse(s["authoritative_cnmi_implementation"])
        self.assertFalse(s["production_influence"])
        self.assertFalse(s["deployment_authorized"])
        self.assertFalse(s["predictive_edge_claimed"])
        self.assertEqual(CNMI_NATIVE_105_34_10, "NOT_CLAIMED")

    def test_research_candidate_can_be_admitted_without_predictive_gain(self):
        c = base_candidate("RESEARCH")
        out = evaluate_candidate(c)
        self.assertTrue(out["research_admissible"])
        self.assertEqual(out["decision"], "RESEARCH_ADMISSIBLE")
        self.assertFalse(out["deployment_authorized"])

    def test_hard_gate_failure_is_noncompensable(self):
        c = base_candidate("PRODUCTION")
        c["hard_gates"]["H1"] = False
        c["positive_empirical_delta"] = 999999
        out = evaluate_candidate(c)
        self.assertFalse(out["research_admissible"])
        self.assertFalse(out["core_admissible"])
        self.assertFalse(out["production_admissible"])
        self.assertIn("HARD_GATE:H1=FAILED_OR_UNPROVEN", out["reasons"])
        self.assertFalse(out["positive_metrics_can_override_hard_gate"])

    def test_missing_applicable_gate_fails_closed(self):
        c = base_candidate("CORE")
        del c["hard_gates"]["H7"]
        out = evaluate_candidate(c)
        self.assertFalse(out["core_admissible"])
        self.assertIn("HARD_GATE:H7=FAILED_OR_UNPROVEN", out["reasons"])

    def test_core_can_pass_without_production_evidence(self):
        c = base_candidate("CORE")
        c["prospective_evaluation"] = False
        out = evaluate_candidate(c)
        self.assertTrue(out["core_admissible"])
        self.assertEqual(out["decision"], "CORE_ADMISSIBLE")
        self.assertFalse(out["deployment_authorized"])

    def test_production_requires_prospective_evaluation(self):
        c = base_candidate("PRODUCTION")
        c["prospective_evaluation"] = False
        out = evaluate_candidate(c)
        self.assertFalse(out["production_admissible"])
        self.assertIn("PRODUCTION:prospective_evaluation=MISSING_OR_FALSE", out["reasons"])

    def test_recoverable_missing_is_pending_not_benign_unknown(self):
        c = base_candidate("PRODUCTION")
        c["provenance_completeness_state"] = "RECOVERABLE_BUT_MISSING"
        out = evaluate_candidate(c)
        self.assertFalse(out["production_admissible"])
        self.assertIn("RECOVERABLE_BUT_MISSING:PROVENANCE_PENDING", out["reasons"])

    def test_deliberate_provenance_destruction_is_integrity_failure(self):
        c = base_candidate("PRODUCTION")
        c["provenance_completeness_state"] = "DELIBERATELY_UNDOCUMENTED_OR_DESTROYED"
        out = evaluate_candidate(c)
        self.assertFalse(out["production_admissible"])
        self.assertIn("INTEGRITY_FAILURE:DELIBERATE_PROVENANCE_LOSS", out["reasons"])

    def test_latent_prior_exposure_blocks_untouched_confirmation(self):
        c = base_candidate("PRODUCTION")
        c["claims_untouched_confirmation"] = True
        c["provenance_completeness_state"] = "LATENT_PRIOR_EXPOSURE_NOT_EXCLUDABLE"
        c["affirmative_access_provenance_argument"] = True
        c["material_prior_exposure_excluded"] = False
        out = evaluate_candidate(c)
        self.assertFalse(out["production_admissible"])
        self.assertIn("PRODUCTION:UNTOUCHED_STATUS_UNAVAILABLE", out["reasons"])
        self.assertIn("PRODUCTION:LATENT_PRIOR_EXPOSURE_NOT_EXCLUDABLE", out["reasons"])

    def test_point_estimate_pareto_cannot_claim_confirmatory_dominance(self):
        c = base_candidate("PRODUCTION")
        c["claims"] = [{
            "type": "EMPIRICAL_SUPERIORITY",
            "requires_confirmatory_pareto": True,
            "pareto_state": "POINT_ESTIMATE_PARETO",
        }]
        out = evaluate_candidate(c)
        self.assertFalse(out["production_admissible"])
        self.assertIn("CLAIM:0=CONFIRMATORY_PARETO_NOT_ESTABLISHED", out["reasons"])

    def test_materiality_requires_protocol_identity_not_universal_margin(self):
        c = base_candidate("PRODUCTION")
        c["claims"] = [{
            "type": "EMPIRICAL_NONINFERIORITY",
            "requires_materiality": True,
        }]
        out = evaluate_candidate(c)
        self.assertFalse(out["production_admissible"])
        self.assertIn("CLAIM:0=MATERIALITY_IDENTITY_MISSING", out["reasons"])
        self.assertIsNone(out["policy"]["universal_materiality_margin"])

    def test_contaminated_materiality_is_rejected(self):
        c = base_candidate("PRODUCTION")
        c["claims"] = [{
            "type": "EMPIRICAL_NONINFERIORITY",
            "requires_materiality": True,
            "materiality_identity": {
                "estimand": "x",
                "target_population": "p",
                "eligibility_rule": "g",
                "outcome_transform": "identity",
                "horizon": "8h",
                "aggregation_rule": "mean",
                "canonical_units": "unit",
                "margin": 1.0,
                "provenance_class": "DEVELOPMENT_INFORMED",
                "provenance_evidence": "documented",
                "freeze_identity": "v1",
                "permitted_claim_semantics": "development-informed only",
                "confirmatory_outcome_used_to_set_margin": True,
            },
        }]
        out = evaluate_candidate(c)
        self.assertFalse(out["production_admissible"])
        self.assertIn("CLAIM:0=MATERIALITY_CONTAMINATED", out["reasons"])

    def test_unknown_claim_type_requires_explicit_evidence_rule(self):
        c = base_candidate("RESEARCH")
        c["claims"] = [{"type": "NEW_MAGIC_CLAIM"}]
        out = evaluate_candidate(c)
        self.assertFalse(out["research_admissible"])
        self.assertIn("CLAIM:0=UNKNOWN_TYPE_WITHOUT_EVIDENCE_RULE", out["reasons"])

    def test_deployment_is_never_automatically_authorized(self):
        c = base_candidate("PRODUCTION")
        out = evaluate_candidate(c)
        self.assertTrue(out["production_admissible"])
        self.assertFalse(out["deployment_authorized"])
        self.assertFalse(out["production_influence"])

    def test_output_is_deterministic_for_same_candidate(self):
        c = base_candidate("PRODUCTION")
        a = evaluate_candidate(copy.deepcopy(c))
        b = evaluate_candidate(copy.deepcopy(c))
        self.assertEqual(a["candidate_digest"], b["candidate_digest"])
        self.assertEqual(a["result_digest"], b["result_digest"])
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
