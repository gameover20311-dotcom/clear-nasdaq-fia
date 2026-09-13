from __future__ import annotations
import unittest
from mfre_v125_shadow.adapters import DPCSEView, MFREInputFrame, ShadowHypothesisView, UMSEView
from mfre_v125_shadow.audit import AuditEvent, AuditLog
from mfre_v125_shadow.contract import IMPLEMENTATION_SCOPE, MFRE_FINAL_PACKAGE_SHA256, MFRE_INCREMENTAL_VALUE, MFRE_VERSION, NOVEL_MATHEMATICS, PRODUCTION_AUTHORIZED, REAL_MARKET_EDGE
from mfre_v125_shadow.controller import MFREShadowController, ShadowRunStatus
from mfre_v125_shadow.types import ActionKind, DeclarationBundle, PrimitiveSpec, RandomnessOwnership

def frame(*,shadow=True,umse=True,integrity=True,dpcse_frozen=False,dpcse_status="NOT_ARMED"):
    return MFREInputFrame(ShadowHypothesisView(shadow,("H1",) if shadow else (),"shadow-digest"),UMSEView(umse,integrity,"STATE",("M1",) if umse else (),"umse-digest"),DPCSEView(dpcse_status,dpcse_frozen,"NO_EDGE",None,None,0,"dpcse-digest"),{"instrument":"NQ","horizon":"8H"})
def declarations():
    return DeclarationBundle((PrimitiveSpec("stop",ActionKind.STOP,0.0,"selection",RandomnessOwnership.NONE_DETERMINISTIC),PrimitiveSpec("read_external",ActionKind.ACQUIRE,1.0,"acquisition",RandomnessOwnership.EXTERNAL_PROVIDER),PrimitiveSpec("compute_countermodel",ActionKind.COMPUTE,1.0,"compute",RandomnessOwnership.ENGINE_OWNED)),4,3,2,"UNSET_DOMAIN_GAMMA_PLACEHOLDER_REQUIRES_FREEZE","MFRE_CONTROL_REPRESENTATION_V1","MFRE_NO_EDGE_TERMINAL_RULE_V1","UNSET_BELLMAN_POLICY_PLACEHOLDER_REQUIRES_FREEZE")
class MFREShadowContractTests(unittest.TestCase):
    def test_exact_freeze_binding_and_scope(self):
        self.assertEqual(MFRE_VERSION,"V1.2.5_FINAL_THEORY_FREEZE"); self.assertEqual(MFRE_FINAL_PACKAGE_SHA256,"3d5b7740f1b739f2ee9ef97999158a69c081ef2adf93bac9f122196700bad1a0"); self.assertEqual(IMPLEMENTATION_SCOPE,"RESEARCH_SHADOW_ONLY"); self.assertFalse(PRODUCTION_AUTHORIZED); self.assertEqual(REAL_MARKET_EDGE,"NOT_TESTED"); self.assertEqual(MFRE_INCREMENTAL_VALUE,"NOT_TESTED"); self.assertEqual(NOVEL_MATHEMATICS,"NOT_PROVEN")
    def test_inert_without_declarations(self):
        r=MFREShadowController().assess(frame()); self.assertEqual(r.status,ShadowRunStatus.INERT_DECLARATIONS_MISSING); self.assertIsNone(r.directional_override); self.assertFalse(r.production_authorized)
    def test_inert_while_dpcse_candidate_not_frozen(self):
        r=MFREShadowController(declarations()).assess(frame(shadow=True,umse=True,dpcse_frozen=False)); self.assertEqual(r.status,ShadowRunStatus.INERT_UPSTREAM_NOT_READY); self.assertIn("DPCSE_CANDIDATE_NOT_FROZEN",r.reasons); self.assertIn("DPCSE_NOT_ARMED",r.reasons)
    def test_ready_means_shadow_only_not_direction_override(self):
        r=MFREShadowController(declarations()).assess(frame(shadow=True,umse=True,integrity=True,dpcse_frozen=True,dpcse_status="ARMED_N0")); self.assertEqual(r.status,ShadowRunStatus.READY_SHADOW); self.assertIsNotNone(r.control_state); self.assertIsNone(r.directional_override); self.assertFalse(r.production_authorized)
    def test_external_provider_eta_is_rejected_and_provenance_required(self):
        p={"event_time":"2026-09-13T15:00:00+00:00","available_time":"2026-09-13T15:00:01+00:00","provider_identity":"TEST_PROVIDER","sequence_id":"1","raw_source_hash":"abc","receive_time":"2026-09-13T15:00:01+00:00"}; e=AuditEvent("read_external","digest",RandomnessOwnership.EXTERNAL_PROVIDER,0.25,provenance=p); self.assertEqual(len(AuditLog().append(e).events),1)
        with self.assertRaisesRegex(ValueError,"ETA_MUST_NOT_BE_RECORDED"): AuditEvent("read_external","digest",RandomnessOwnership.EXTERNAL_PROVIDER,0.25,0.5,p)
    def test_engine_owned_eta_is_required(self):
        with self.assertRaisesRegex(ValueError,"ENGINE_OWNED_ETA_REQUIRED"): AuditEvent("compute_countermodel","digest",RandomnessOwnership.ENGINE_OWNED,0.2)
if __name__=="__main__": unittest.main()
