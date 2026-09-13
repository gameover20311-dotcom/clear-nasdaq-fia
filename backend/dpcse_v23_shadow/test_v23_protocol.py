from __future__ import annotations
import unittest
from dpcse_v23_shadow.campaign import bootstrap_manifest, build_armed_seal, verify_armed_seal
from dpcse_v23_shadow.candidate import CandidateIdentity, CandidateModelNotFrozen, UnfrozenCandidate
from dpcse_v23_shadow.decision import evaluate_shadow_decision
from dpcse_v23_shadow.environment import EnvironmentState, ResolvedTopLabel, environment_state, relative_error_alarm
from dpcse_v23_shadow.evaluation import Paired8HRow, pilot_diagnostics
from dpcse_v23_shadow.spec import DIRECTIONAL_MARGIN_MIN, ENV_ARM_MIN_RESOLVED, PILOT_ALPHA, PILOT_N_TARGET, PRIMARY_HORIZON, SPEC_HASH

def rows_from_errors(reference_errors: int, current_errors: int):
    vals = [False] * reference_errors + [True] * (20 - reference_errors) + [False] * current_errors + [True] * (10 - current_errors)
    return [ResolvedTopLabel(i, ok) for i, ok in enumerate(vals)]

class V23ProtocolTests(unittest.TestCase):
    def test_frozen_constants(self):
        self.assertEqual((PILOT_N_TARGET, PILOT_ALPHA, PRIMARY_HORIZON, ENV_ARM_MIN_RESOLVED, DIRECTIONAL_MARGIN_MIN), (50, 0.0, "8H", 30, 0.10)); self.assertEqual(len(SPEC_HASH), 64)
    def test_exact_integer_environment_alarm_boundary(self):
        self.assertTrue(relative_error_alarm(7, 7)); self.assertFalse(relative_error_alarm(8, 7)); self.assertFalse(relative_error_alarm(0, 6))
    def test_environment_warmup_stale_shift_valid(self):
        self.assertIs(environment_state([ResolvedTopLabel(i, True) for i in range(29)], current_checkpoint_index=29).state, EnvironmentState.WARMUP)
        self.assertIs(environment_state(rows_from_errors(0, 0), current_checkpoint_index=31).state, EnvironmentState.STALE)
        self.assertIs(environment_state(rows_from_errors(7, 7), current_checkpoint_index=30).state, EnvironmentState.SHIFT_DETECTED)
        self.assertIs(environment_state(rows_from_errors(2, 2), current_checkpoint_index=30).state, EnvironmentState.VALID)
    def test_three_runtime_gates(self):
        env = environment_state(rows_from_errors(2, 2), current_checkpoint_index=30)
        self.assertEqual(evaluate_shadow_decision(p_bull=.60, p_bear=.40, availability_integrity_pass=False, environment=env).decision, "NO_EDGE")
        self.assertEqual(evaluate_shadow_decision(p_bull=.54, p_bear=.46, availability_integrity_pass=True, environment=env).reason, "NO_EDGE_AMBIGUOUS")
        self.assertEqual(evaluate_shadow_decision(p_bull=.55, p_bear=.45, availability_integrity_pass=True, environment=env).decision, "BULL")
        self.assertEqual(evaluate_shadow_decision(p_bull=.45, p_bear=.55, availability_integrity_pass=True, environment=env).decision, "BEAR")
    def test_candidate_fails_closed_until_actual_model_freeze(self):
        with self.assertRaises(CandidateModelNotFrozen): UnfrozenCandidate().predict_8h({"x": 1.0})
        m = bootstrap_manifest(); self.assertEqual(m["status"], "NOT_ARMED"); self.assertEqual(m["locked_rows"], 0)
    def test_future_armed_seal_starts_at_n_zero(self):
        ident = CandidateIdentity("TEST_ONLY_CANDIDATE", "a" * 64, "b" * 64)
        seal = build_armed_seal(candidate=ident, registered_at_utc="2026-09-13T15:00:00+00:00")
        self.assertTrue(verify_armed_seal(seal)); self.assertEqual(seal["locked_rows_at_seal"], 0); self.assertEqual(seal["resolved_rows_at_seal"], 0)
        mutated = dict(seal); mutated["locked_rows_at_seal"] = 1; self.assertFalse(verify_armed_seal(mutated))
    def test_primary_brier_keeps_no_edge_rows(self):
        d = pilot_diagnostics([Paired8HRow(.50, .60, True, candidate_decision="BULL"), Paired8HRow(.50, .51, False, candidate_decision="NO_EDGE")])
        self.assertEqual((d.n_all_eligible, d.n_directional_committed), (2, 1)); self.assertAlmostEqual(d.directional_gate_pass_rate, .5); self.assertFalse(d.confirmatory); self.assertFalse(d.promotion_eligible); self.assertEqual(d.predictive_edge, "NOT_PROVEN")

if __name__ == "__main__": unittest.main(verbosity=2)
