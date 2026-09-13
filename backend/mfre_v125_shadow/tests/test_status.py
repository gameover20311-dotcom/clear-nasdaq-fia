from __future__ import annotations

import unittest

from mfre_v125_shadow.adapters import DPCSEView, MFREInputFrame, ShadowHypothesisView, UMSEView
from mfre_v125_shadow.status import build_truth_status
from mfre_v125_shadow.types import ActionKind, DeclarationBundle, PrimitiveSpec, RandomnessOwnership


def _frame(*, shadow=True, hypotheses=("H1",), umse=True, integrity=True, dpcse_frozen=False, dpcse_status="NOT_ARMED"):
    return MFREInputFrame(
        shadow=ShadowHypothesisView(shadow, hypotheses if shadow else (), "shadow-digest", "DISCOVERY_ONLY_NOT_PROVEN"),
        umse=UMSEView(umse, integrity, "UMSE_V2_SHADOW_DIAGNOSTICS", ("queue_survival:OBSERVED",) if umse else (), "umse-digest", "RESEARCH_DIAGNOSTICS_ONLY_NO_PREDICTIVE_MAPPING"),
        dpcse=DPCSEView(dpcse_status, dpcse_frozen, "NO_EDGE", None, None, 0, "dpcse-digest", "NOT_PROVEN"),
        context={"instrument": "NQ", "horizon": "8H"},
    )


def _draft_declarations():
    return DeclarationBundle(
        primitives=(PrimitiveSpec("stop", ActionKind.STOP, 0.0, "selection", RandomnessOwnership.NONE_DETERMINISTIC),),
        compute_budget=1,
        acquisition_budget=1,
        selection_budget=1,
        gamma_theta_id="UNSET_GAMMA_REQUIRES_FREEZE",
        phi_id="UNSET_PHI_REQUIRES_FREEZE",
        delta_stop_id="UNSET_STOP_REQUIRES_FREEZE",
        bellman_policy_id="UNSET_BELLMAN_REQUIRES_FREEZE",
    )


def _frozen_fixture():
    # Synthetic fixture only; never used as a real scientific declaration bundle.
    return DeclarationBundle(
        primitives=(
            PrimitiveSpec("stop", ActionKind.STOP, 0.0, "selection", RandomnessOwnership.NONE_DETERMINISTIC, "1" * 64),
            PrimitiveSpec("acquire", ActionKind.ACQUIRE, 1.0, "acquisition", RandomnessOwnership.EXTERNAL_PROVIDER, "2" * 64),
            PrimitiveSpec("compute", ActionKind.COMPUTE, 1.0, "compute", RandomnessOwnership.ENGINE_OWNED, "3" * 64),
        ),
        compute_budget=2,
        acquisition_budget=2,
        selection_budget=2,
        gamma_theta_id="TEST_ONLY_GAMMA",
        phi_id="TEST_ONLY_PHI",
        delta_stop_id="TEST_ONLY_STOP",
        bellman_policy_id="TEST_ONLY_BELLMAN",
        gamma_theta_fingerprint="4" * 64,
        phi_fingerprint="5" * 64,
        delta_stop_fingerprint="6" * 64,
        bellman_policy_fingerprint="7" * 64,
        working_measure_id="TEST_ONLY_P",
        working_measure_fingerprint="8" * 64,
        k_max=2,
        c_a=0.3,
        tie_break=("Bull", "Bear", "NO_EDGE"),
        l10_parameters=(("kappa", "5"), ("ell", "4"), ("B", "999"), ("seed", "20260913"), ("autocorrelation_band", "0.10"), ("evaluation_window", "50")),
    )


class MFRETruthStatusTests(unittest.TestCase):
    def test_missing_declarations_never_looks_ready(self):
        s = build_truth_status(_frame())
        self.assertEqual(s["declaration_status"], "MISSING")
        self.assertEqual(s["run_status"], "INERT_DECLARATIONS_MISSING")
        self.assertFalse(s["shadow_runtime_ready"])
        self.assertFalse(s["dashboard_decision_ready"])
        self.assertIn("MFRE_DECLARATION_BUNDLE_MISSING", s["research_blockers"])

    def test_unfrozen_declarations_never_get_protocol_identity(self):
        s = build_truth_status(_frame(dpcse_frozen=True, dpcse_status="ARMED_N0"), _draft_declarations())
        self.assertEqual(s["declaration_status"], "UNFROZEN")
        self.assertEqual(s["run_status"], "INERT_DECLARATIONS_UNFROZEN")
        self.assertIsNone(s["protocol_identity"])
        self.assertFalse(s["dashboard_decision_ready"])

    def test_dpcse_not_armed_is_visible_blocker(self):
        s = build_truth_status(_frame(), _frozen_fixture())
        self.assertEqual(s["declaration_status"], "FROZEN")
        self.assertIn("DPCSE_CANDIDATE_NOT_FROZEN", s["research_blockers"])
        self.assertIn("DPCSE_NOT_ARMED", s["research_blockers"])
        self.assertFalse(s["shadow_contract_ready"])

    def test_shadow_or_umse_failure_is_visible(self):
        s = build_truth_status(_frame(shadow=False, umse=True, integrity=False, dpcse_frozen=True, dpcse_status="ARMED_N0"), _frozen_fixture())
        self.assertIn("SHADOW_LAB_UNAVAILABLE", s["research_blockers"])
        self.assertIn("UMSE_INTEGRITY_FAIL", s["research_blockers"])
        self.assertFalse(s["shadow_runtime_ready"])

    def test_contract_ready_still_reports_execution_engine_unbound(self):
        s = build_truth_status(_frame(dpcse_frozen=True, dpcse_status="ARMED_N0"), _frozen_fixture())
        self.assertEqual(s["run_status"], "READY_SHADOW_CONTRACT_ONLY")
        self.assertTrue(s["shadow_contract_ready"])
        self.assertFalse(s["execution_engine_bound"])
        self.assertFalse(s["shadow_runtime_ready"])
        self.assertIn("MFRE_EXECUTION_ENGINE_NOT_YET_BOUND", s["research_blockers"])
        self.assertFalse(s["dashboard_decision_ready"])

    def test_status_never_claims_edge_or_production_authority(self):
        s = build_truth_status(_frame(dpcse_frozen=True, dpcse_status="ARMED_N0"), _frozen_fixture())
        self.assertEqual(s["theory_freeze"], "FINAL_FREEZE_PASS")
        self.assertEqual(s["implementation_scope"], "RESEARCH_SHADOW_ONLY")
        self.assertFalse(s["production_authorized"])
        self.assertEqual(s["decision_authority"], "NONE")
        self.assertEqual(s["predictive_edge"], "NOT_PROVEN")
        self.assertEqual(s["real_market_edge"], "NOT_TESTED")
        self.assertEqual(s["mfre_incremental_value"], "NOT_TESTED")
        self.assertIsNone(s["directional_override"])
        self.assertIn("MFRE_PRODUCTION_AUTHORITY_NOT_GRANTED", s["decision_blockers"])
        self.assertIn("PREDICTIVE_EDGE_NOT_PROVEN", s["decision_blockers"])


if __name__ == "__main__":
    unittest.main()
