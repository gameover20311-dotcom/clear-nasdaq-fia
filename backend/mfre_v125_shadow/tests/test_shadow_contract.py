from __future__ import annotations

import unittest

from mfre_v125_shadow.adapters import DPCSEView, MFREInputFrame, ShadowHypothesisView, UMSEView
from mfre_v125_shadow.audit import AuditEvent, AuditLog
from mfre_v125_shadow.contract import (
    IMPLEMENTATION_SCOPE,
    MFRE_FINAL_PACKAGE_SHA256,
    MFRE_INCREMENTAL_VALUE,
    MFRE_VERSION,
    NOVEL_MATHEMATICS,
    PRODUCTION_AUTHORIZED,
    REAL_MARKET_EDGE,
)
from mfre_v125_shadow.controller import MFREShadowController, ShadowRunStatus
from mfre_v125_shadow.types import (
    ActionKind,
    DeclarationBundle,
    PrimitiveSpec,
    RandomnessOwnership,
)


def frame(*, shadow=True, umse=True, integrity=True, dpcse_frozen=False, dpcse_status="NOT_ARMED"):
    return MFREInputFrame(
        shadow=ShadowHypothesisView(shadow, ("H1",) if shadow else (), "shadow-digest"),
        umse=UMSEView(umse, integrity, "STATE", ("M1",) if umse else (), "umse-digest"),
        dpcse=DPCSEView(
            status=dpcse_status,
            candidate_model_frozen=dpcse_frozen,
            decision="NO_EDGE",
            p_bull=None,
            p_bear=None,
            locked_rows=0,
            source_digest="dpcse-digest",
        ),
        context={"instrument": "NQ", "horizon": "8H"},
    )


def declarations():
    return DeclarationBundle(
        primitives=(
            PrimitiveSpec("stop", ActionKind.STOP, 0.0, "selection", RandomnessOwnership.NONE_DETERMINISTIC),
            PrimitiveSpec("read_external", ActionKind.ACQUIRE, 1.0, "acquisition", RandomnessOwnership.EXTERNAL_PROVIDER),
            PrimitiveSpec("compute_countermodel", ActionKind.COMPUTE, 1.0, "compute", RandomnessOwnership.ENGINE_OWNED),
        ),
        compute_budget=4,
        acquisition_budget=3,
        selection_budget=2,
        gamma_theta_id="UNSET_DOMAIN_GAMMA_PLACEHOLDER_REQUIRES_FREEZE",
        phi_id="MFRE_CONTROL_REPRESENTATION_V1",
        delta_stop_id="MFRE_NO_EDGE_TERMINAL_RULE_V1",
        bellman_policy_id="UNSET_BELLMAN_POLICY_PLACEHOLDER_REQUIRES_FREEZE",
    )


class MFREShadowContractTests(unittest.TestCase):
    def test_exact_freeze_binding_and_scope(self):
        self.assertEqual(MFRE_VERSION, "V1.2.5_FINAL_THEORY_FREEZE")
        self.assertEqual(MFRE_FINAL_PACKAGE_SHA256, "3d5b7740f1b739f2ee9ef97999158a69c081ef2adf93bac9f122196700bad1a0")
        self.assertEqual(IMPLEMENTATION_SCOPE, "RESEARCH_SHADOW_ONLY")
        self.assertFalse(PRODUCTION_AUTHORIZED)
        self.assertEqual(REAL_MARKET_EDGE, "NOT_TESTED")
        self.assertEqual(MFRE_INCREMENTAL_VALUE, "NOT_TESTED")
        self.assertEqual(NOVEL_MATHEMATICS, "NOT_PROVEN")

    def test_inert_without_declarations(self):
        r = MFREShadowController().assess(frame())
        self.assertEqual(r.status, ShadowRunStatus.INERT_DECLARATIONS_MISSING)
        self.assertIsNone(r.directional_override)
        self.assertFalse(r.production_authorized)

    def test_inert_while_dpcse_candidate_not_frozen(self):
        r = MFREShadowController(declarations()).assess(frame(shadow=True, umse=True, dpcse_frozen=False))
        self.assertEqual(r.status, ShadowRunStatus.INERT_UPSTREAM_NOT_READY)
        self.assertIn("DPCSE_CANDIDATE_NOT_FROZEN", r.reasons)
        self.assertIn("DPCSE_NOT_ARMED", r.reasons)

    def test_ready_means_shadow_only_not_direction_override(self):
        r = MFREShadowController(declarations()).assess(
            frame(shadow=True, umse=True, integrity=True, dpcse_frozen=True, dpcse_status="ARMED_N0")
        )
        self.assertEqual(r.status, ShadowRunStatus.READY_SHADOW)
        self.assertIsNotNone(r.control_state)
        self.assertIsNone(r.directional_override)
        self.assertFalse(r.production_authorized)

    def test_external_provider_eta_is_rejected_and_provenance_required(self):
        provenance = {
            "event_time": "2026-09-13T15:00:00+00:00",
            "available_time": "2026-09-13T15:00:01+00:00",
            "provider_identity": "TEST_PROVIDER",
            "sequence_id": "1",
            "raw_source_hash": "abc",
            "receive_time": "2026-09-13T15:00:01+00:00",
        }
        event = AuditEvent(
            action_id="read_external",
            observed_output_digest="digest",
            ownership=RandomnessOwnership.EXTERNAL_PROVIDER,
            fresh_xi=0.25,
            provenance=provenance,
        )
        log = AuditLog().append(event)
        self.assertEqual(len(log.events), 1)
        with self.assertRaisesRegex(ValueError, "ETA_MUST_NOT_BE_RECORDED"):
            AuditEvent(
                action_id="read_external",
                observed_output_digest="digest",
                ownership=RandomnessOwnership.EXTERNAL_PROVIDER,
                fresh_xi=0.25,
                eta_if_owned=0.5,
                provenance=provenance,
            )

    def test_engine_owned_eta_is_required(self):
        with self.assertRaisesRegex(ValueError, "ENGINE_OWNED_ETA_REQUIRED"):
            AuditEvent(
                action_id="compute_countermodel",
                observed_output_digest="digest",
                ownership=RandomnessOwnership.ENGINE_OWNED,
                fresh_xi=0.2,
            )

    def test_empty_shadow_hypotheses_fail_closed(self):
        r = MFREShadowController(declarations()).assess(
            MFREInputFrame(
                shadow=ShadowHypothesisView(True, (), "shadow-digest"),
                umse=UMSEView(True, True, "STATE", ("M1",), "umse-digest"),
                dpcse=DPCSEView("ARMED_N0", True, "NO_EDGE", None, None, 0, "dpcse-digest"),
                context={"instrument": "NQ", "horizon": "8H"},
            )
        )
        self.assertEqual(r.status, ShadowRunStatus.INERT_UPSTREAM_NOT_READY)
        self.assertIn("SHADOW_HYPOTHESES_EMPTY", r.reasons)

    def test_source_pinned_shadow_adapter_keeps_hypotheses_exploratory(self):
        from mfre_v125_shadow.upstream import UPSTREAM_PROVENANCE, shadow_view_from_report
        report = {
            "lab_version": "SIMONS_SHADOW_LAB_V2_HYBRID",
            "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
            "lock_time_structural_barrier": True,
            "automatic_strategy_selection": False,
            "automatic_production_promotion": False,
            "predictive_edge_proven": False,
            "profitability_proven": False,
            "h8": {"transitions": {"transitions": [
                {"transition": "A -> B", "status": "EXPLORATORY_ONLY_NOT_PROVEN"}
            ]}},
        }
        view = shadow_view_from_report(report)
        self.assertTrue(view.available)
        self.assertEqual(view.hypotheses, ("H8_TRANSITION::A -> B",))
        self.assertEqual(UPSTREAM_PROVENANCE["shadow_lab"]["branch_head"], "6c52e44b516ec9d707e3acbc3b958fe4dd9d6fe7")

    def test_shadow_adapter_rejects_edge_or_promotion_escalation(self):
        from mfre_v125_shadow.upstream import shadow_view_from_report
        report = {
            "lab_version": "SIMONS_SHADOW_LAB_V2_HYBRID",
            "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
            "lock_time_structural_barrier": True,
            "automatic_strategy_selection": False,
            "automatic_production_promotion": True,
            "predictive_edge_proven": False,
            "profitability_proven": False,
            "h8": {"transitions": {"transitions": []}},
        }
        self.assertFalse(shadow_view_from_report(report).available)

    def test_umse_adapter_requires_explicit_integrity_and_no_status_escalation(self):
        from mfre_v125_shadow.upstream import umse_view_from_v2_diagnostics
        diag = {
            "evidence_hash": "abc123",
            "predictive_mapping_frozen": False,
            "predictive_edge_proven": False,
            "production_effect": False,
            "queue_survival": {"status": "OBSERVED"},
            "orderbook_memory": {"status": "INSUFFICIENT_DATA"},
            "resistance_field": {"status": "OBSERVED"},
            "information_velocity": {"status": "OBSERVED"},
            "leadlag_evidence": {"status": "NOT_IDENTIFIABLE"},
            "cross_scale_transport": {"status": "INSUFFICIENT_DATA"},
        }
        view = umse_view_from_v2_diagnostics(diag, integrity_pass=True)
        self.assertTrue(view.available)
        self.assertTrue(view.integrity_pass)
        self.assertIn("queue_survival:OBSERVED", view.mechanisms)
        bad = dict(diag)
        bad["predictive_edge_proven"] = True
        self.assertFalse(umse_view_from_v2_diagnostics(bad, integrity_pass=True).available)

    def test_dpcse_bootstrap_adapter_preserves_not_armed(self):
        from mfre_v125_shadow.upstream import dpcse_view_from_bootstrap
        manifest = {
            "status": "NOT_ARMED",
            "candidate_model": None,
            "locked_rows": 0,
            "predictive_edge": "NOT_PROVEN",
        }
        view = dpcse_view_from_bootstrap(manifest)
        self.assertFalse(view.candidate_model_frozen)
        self.assertFalse(view.armed)
        self.assertEqual(view.predictive_edge, "NOT_PROVEN")


if __name__ == "__main__":
    unittest.main()
