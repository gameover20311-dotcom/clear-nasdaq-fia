import copy
import unittest

from research.cnmi_shadow.adapter import (
    ADAPTER_ID,
    CNMI_NATIVE_105_34_10,
    HARD_GATES,
    evaluate_candidate,
    status,
)


def base_candidate(level="PRODUCTION"):
    return {
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


def valid_materiality_identity():
    return {
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
        "confirmatory_outcome_used_to_set_margin": False,
    }


class CNMIShadowTests(unittest.TestCase):
    def test_identity_is_explicitly_nonauthoritative(self):
        s = status()
        self.assertEqual(s["adapter_id"], ADAPTER_ID)
        self.assertFalse(s["authoritative_cnmi_implementation"])
        self.assertFalse(s["production_influence"])
        self.assertFalse(s["deployment_authorized"])
        self.assertFalse(s["predictive_edge_claimed"])
        self.assertFalse(s["external_production_verifier_bound"])
        self.assertEqual(CNMI_NATIVE_105_34_10, "NOT_CLAIMED")
        self.assertTrue(s["policy"]["bare_candidate_self_attestation_never_enough"])
        self.assertTrue(s["policy"]["requested_level_caps_evaluation_scope"])

    def test_research_candidate_can_be_admitted_without_predictive_gain(self):
        out = evaluate_candidate(base_candidate("RESEARCH"))
        self.assertTrue(out["research_admissible"])
        self.assertEqual(out["decision"], "RESEARCH_ADMISSIBLE")
        self.assertFalse(out["core_admissible"])
        self.assertFalse(out["production_structurally_eligible"])
        self.assertFalse(out["deployment_authorized"])

    def test_research_request_cannot_surface_production_eligibility(self):
        c = base_candidate("RESEARCH")
        c["applicable_hard_gates"] = ["H1"]
        c["hard_gates"] = {"H1": True}
        out = evaluate_candidate(c)
        self.assertTrue(out["research_admissible"])
        self.assertFalse(out["core_admissible"])
        self.assertFalse(out["production_structurally_eligible"])
        self.assertEqual(out["highest_structural_level"], "RESEARCH")

    def test_invalid_requested_level_cannot_earn_any_level(self):
        out = evaluate_candidate(base_candidate("MAGIC"))
        self.assertFalse(out["research_admissible"])
        self.assertFalse(out["core_admissible"])
        self.assertFalse(out["production_structurally_eligible"])
        self.assertFalse(out["production_admissible"])
        self.assertEqual(out["highest_earned_level"], "NONE")
        self.assertEqual(out["highest_structural_level"], "NONE")
        self.assertIn("REQUESTED_LEVEL:INVALID_OR_MISSING", out["reasons"])

    def test_core_can_pass_without_production_evidence(self):
        c = base_candidate("CORE")
        c["prospective_evaluation"] = False
        out = evaluate_candidate(c)
        self.assertTrue(out["core_admissible"])
        self.assertEqual(out["decision"], "CORE_ADMISSIBLE")
        self.assertFalse(out["production_structurally_eligible"])
        self.assertFalse(out["deployment_authorized"])

    def test_hard_gate_failure_is_noncompensable(self):
        c = base_candidate()
        c["hard_gates"]["H1"] = False
        c["positive_empirical_delta"] = 999999
        out = evaluate_candidate(c)
        self.assertFalse(out["research_admissible"])
        self.assertFalse(out["core_admissible"])
        self.assertFalse(out["production_structurally_eligible"])
        self.assertFalse(out["production_admissible"])
        self.assertIn("HARD_GATE:H1=FAILED_OR_UNPROVEN", out["reasons"])
        self.assertFalse(out["positive_metrics_can_override_hard_gate"])

    def test_every_production_hard_gate_is_noncompensable(self):
        for gate in HARD_GATES:
            with self.subTest(gate=gate):
                c = base_candidate()
                c["hard_gates"][gate] = False
                out = evaluate_candidate(c)
                self.assertFalse(out["production_structurally_eligible"])
                self.assertIn(f"HARD_GATE:{gate}=FAILED_OR_UNPROVEN", out["reasons"])

    def test_production_cannot_omit_hard_gate_from_applicable_list(self):
        c = base_candidate()
        c["applicable_hard_gates"].remove("H9")
        out = evaluate_candidate(c)
        self.assertFalse(out["production_structurally_eligible"])
        self.assertTrue(
            any(r.startswith("PRODUCTION:HARD_GATES_NOT_DECLARED:") and "H9" in r for r in out["reasons"])
        )

    def test_duplicate_applicable_gate_fails_closed(self):
        c = base_candidate()
        c["applicable_hard_gates"].append("H1")
        out = evaluate_candidate(c)
        self.assertFalse(out["production_structurally_eligible"])
        self.assertIn("APPLICABLE_HARD_GATES:DUPLICATE", out["reasons"])

    def test_unknown_gate_fails_closed(self):
        c = base_candidate()
        c["applicable_hard_gates"].append("H99")
        c["hard_gates"]["H99"] = True
        out = evaluate_candidate(c)
        self.assertFalse(out["production_structurally_eligible"])
        self.assertIn("HARD_GATE:H99=UNKNOWN", out["reasons"])

    def test_production_requires_prospective_evaluation(self):
        c = base_candidate()
        c["prospective_evaluation"] = False
        out = evaluate_candidate(c)
        self.assertFalse(out["production_structurally_eligible"])
        self.assertFalse(out["production_admissible"])
        self.assertIn("PRODUCTION:prospective_evaluation=MISSING_OR_FALSE", out["reasons"])

    def test_all_incomplete_provenance_states_block_production(self):
        blocked = (
            "INCOMPLETE_KNOWN",
            "HISTORICALLY_UNRECOVERABLE",
            "RECOVERABLE_BUT_MISSING",
            "DELIBERATELY_UNDOCUMENTED_OR_DESTROYED",
            "LATENT_PRIOR_EXPOSURE_NOT_EXCLUDABLE",
        )
        for state in blocked:
            with self.subTest(state=state):
                c = base_candidate()
                c["provenance_completeness_state"] = state
                out = evaluate_candidate(c)
                self.assertFalse(out["production_structurally_eligible"])
                self.assertIn(f"PRODUCTION:PROVENANCE_NOT_COMPLETE:{state}", out["reasons"])

    def test_complete_controlled_access_boundary_can_be_structurally_eligible(self):
        c = base_candidate()
        c["provenance_completeness_state"] = "COMPLETE_BY_CONTROLLED_ACCESS_BOUNDARY"
        out = evaluate_candidate(c)
        self.assertTrue(out["production_structurally_eligible"])
        self.assertFalse(out["production_admissible"])

    def test_latent_prior_exposure_blocks_untouched_confirmation(self):
        c = base_candidate()
        c["claims_untouched_confirmation"] = True
        c["provenance_completeness_state"] = "LATENT_PRIOR_EXPOSURE_NOT_EXCLUDABLE"
        c["affirmative_access_provenance_argument"] = True
        c["material_prior_exposure_excluded"] = False
        out = evaluate_candidate(c)
        self.assertFalse(out["production_structurally_eligible"])
        self.assertIn("PRODUCTION:UNTOUCHED_STATUS_UNAVAILABLE", out["reasons"])
        self.assertIn("PRODUCTION:LATENT_PRIOR_EXPOSURE_NOT_EXCLUDABLE", out["reasons"])

    def test_point_estimate_pareto_cannot_claim_confirmatory_dominance(self):
        c = base_candidate()
        c["claims"] = [{
            "type": "EMPIRICAL_SUPERIORITY",
            "requires_confirmatory_pareto": True,
            "pareto_state": "POINT_ESTIMATE_PARETO",
        }]
        out = evaluate_candidate(c)
        self.assertFalse(out["production_structurally_eligible"])
        self.assertIn("CLAIM:0=CONFIRMATORY_PARETO_NOT_ESTABLISHED", out["reasons"])

    def test_materiality_requires_protocol_identity_not_universal_margin(self):
        c = base_candidate()
        c["claims"] = [{"type": "EMPIRICAL_NONINFERIORITY", "requires_materiality": True}]
        out = evaluate_candidate(c)
        self.assertFalse(out["production_structurally_eligible"])
        self.assertIn("CLAIM:0=MATERIALITY_IDENTITY_MISSING", out["reasons"])
        self.assertIsNone(out["policy"]["universal_materiality_margin"])

    def test_materiality_identity_rejects_empty_required_values(self):
        c = base_candidate()
        identity = valid_materiality_identity()
        identity["freeze_identity"] = "   "
        identity["provenance_evidence"] = None
        c["claims"] = [{
            "type": "EMPIRICAL_NONINFERIORITY",
            "requires_materiality": True,
            "materiality_identity": identity,
        }]
        out = evaluate_candidate(c)
        self.assertFalse(out["production_structurally_eligible"])
        marker = next(r for r in out["reasons"] if r.startswith("CLAIM:0=MATERIALITY_IDENTITY_EMPTY:"))
        self.assertIn("freeze_identity", marker)
        self.assertIn("provenance_evidence", marker)

    def test_contaminated_materiality_is_rejected(self):
        c = base_candidate()
        identity = valid_materiality_identity()
        identity["confirmatory_outcome_used_to_set_margin"] = True
        c["claims"] = [{
            "type": "EMPIRICAL_NONINFERIORITY",
            "requires_materiality": True,
            "materiality_identity": identity,
        }]
        out = evaluate_candidate(c)
        self.assertFalse(out["production_structurally_eligible"])
        self.assertIn("CLAIM:0=MATERIALITY_CONTAMINATED", out["reasons"])

    def test_unknown_claim_type_fails_even_with_self_supplied_rule(self):
        c = base_candidate("RESEARCH")
        c["claims"] = [{
            "type": "NEW_MAGIC_CLAIM",
            "explicit_evidence_rule": {"anything": "truthy"},
        }]
        out = evaluate_candidate(c)
        self.assertFalse(out["research_admissible"])
        self.assertIn("CLAIM:0=UNKNOWN_TYPE_UNREGISTERED", out["reasons"])

    def test_bare_self_attestation_never_becomes_production_admission(self):
        out = evaluate_candidate(base_candidate())
        self.assertTrue(out["production_structurally_eligible"])
        self.assertEqual(out["highest_structural_level"], "PRODUCTION")
        self.assertEqual(out["highest_earned_level"], "CORE")
        self.assertFalse(out["production_admissible"])
        self.assertEqual(out["decision"], "PRODUCTION_NOT_ADMISSIBLE")
        self.assertIn("PRODUCTION:EXTERNAL_VERIFIER_NOT_BOUND", out["reasons"])
        self.assertEqual(out["evidence_independence_status"], "DEPENDENCE_NOT_EXCLUDABLE")

    def test_positive_metrics_cannot_override_external_verifier_boundary(self):
        c = base_candidate()
        c["positive_empirical_delta"] = 10**18
        c["claimed_confidence"] = 1.0
        out = evaluate_candidate(c)
        self.assertTrue(out["production_structurally_eligible"])
        self.assertFalse(out["production_admissible"])
        self.assertIn("PRODUCTION:EXTERNAL_VERIFIER_NOT_BOUND", out["reasons"])

    def test_malformed_candidate_abstains(self):
        out = evaluate_candidate(["not", "a", "mapping"])
        self.assertFalse(out["ok"])
        self.assertEqual(out["decision"], "ABSTAIN_MALFORMED_CANDIDATE")
        self.assertFalse(out["production_admissible"])

    def test_output_is_deterministic_for_same_candidate(self):
        c = base_candidate()
        a = evaluate_candidate(copy.deepcopy(c))
        b = evaluate_candidate(copy.deepcopy(c))
        self.assertEqual(a["candidate_digest"], b["candidate_digest"])
        self.assertEqual(a["result_digest"], b["result_digest"])
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
