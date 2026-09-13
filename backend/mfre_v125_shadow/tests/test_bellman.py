from __future__ import annotations

from decimal import Decimal
import unittest

from mfre_v125_shadow.bellman import ExactFiniteSupportBellmanEngine, TerminalEvaluation, Transition
from mfre_v125_shadow.types import ActionKind, ControlState, DeclarationBundle, PrimitiveSpec, RandomnessOwnership


def declarations(tie_break=("first", "second", "stop")):
    return DeclarationBundle(
        primitives=(
            PrimitiveSpec("stop", ActionKind.STOP, 0.0, "selection", RandomnessOwnership.NONE_DETERMINISTIC, "1"*64),
            PrimitiveSpec("first", ActionKind.COMPUTE, 1.0, "compute", RandomnessOwnership.ENGINE_OWNED, "2"*64),
            PrimitiveSpec("second", ActionKind.COMPUTE, 1.0, "compute", RandomnessOwnership.ENGINE_OWNED, "3"*64),
        ),
        compute_budget=2, acquisition_budget=0, selection_budget=0,
        gamma_theta_id="TEST_GAMMA", phi_id="TEST_PHI", delta_stop_id="TEST_STOP", bellman_policy_id="TEST_BELLMAN",
        gamma_theta_fingerprint="4"*64, phi_fingerprint="5"*64, delta_stop_fingerprint="6"*64, bellman_policy_fingerprint="7"*64,
        working_measure_id="TEST_P", working_measure_fingerprint="8"*64,
        k_max=2, c_a=0.3, tie_break=tie_break,
        l10_parameters=(("kappa","5"),("ell","4"),("B","999"),("seed","20260913"),("autocorrelation_band","0.10"),("evaluation_window","50")),
    )


class TwoStepRuntime:
    def terminal_evaluation(self, state):
        return TerminalEvaluation("NO_EDGE", Decimal("0") if len(state.history) >= 2 else Decimal("0.3"))

    def admissible_actions(self, state):
        if len(state.history) == 0:
            return ("first",)
        if len(state.history) == 1:
            return ("second",)
        return ()

    def transition_support(self, state, action_id):
        primitive = {p.action_id:p for p in declarations().primitives}[action_id]
        nxt = state.append(action_id=action_id, output_digest=action_id+"-out", kind=primitive.kind, budget_name=primitive.budget_name, cost=primitive.cost)
        return (Transition(Decimal("1"), nxt),)


class TieRuntime:
    def terminal_evaluation(self, state):
        return TerminalEvaluation("NO_EDGE", Decimal("0.2"))

    def admissible_actions(self, state):
        return ("first",) if not state.history else ()

    def transition_support(self, state, action_id):
        primitive = {p.action_id:p for p in declarations().primitives}[action_id]
        nxt = state.append(action_id=action_id, output_digest="same", kind=primitive.kind, budget_name=primitive.budget_name, cost=primitive.cost)
        return (Transition(Decimal("1"), nxt),)


class MFREBellmanTests(unittest.TestCase):
    def test_two_step_value_beats_greedy_stop(self):
        solution = ExactFiniteSupportBellmanEngine(declarations(), TwoStepRuntime()).solve()
        self.assertEqual(solution.value, Decimal("0"))
        self.assertEqual(solution.choice_action_id, "first")
        self.assertFalse(solution.stop)

    def test_declared_tie_break_is_deterministic(self):
        action_first = ExactFiniteSupportBellmanEngine(declarations(("first","second","stop")), TieRuntime()).solve()
        stop_first = ExactFiniteSupportBellmanEngine(declarations(("stop","first","second")), TieRuntime()).solve()
        self.assertEqual(action_first.value, Decimal("0.2"))
        self.assertEqual(action_first.choice_action_id, "first")
        self.assertEqual(stop_first.choice_action_id, "stop")
        self.assertTrue(stop_first.stop)
        self.assertEqual(stop_first.terminal_action, "NO_EDGE")

    def test_exhausted_budget_forces_stop(self):
        state = ControlState((), 0.0, 0.0, 0.0)
        solution = ExactFiniteSupportBellmanEngine(declarations(), TwoStepRuntime()).solve(state)
        self.assertTrue(solution.stop)
        self.assertEqual(solution.choice_action_id, "stop")

    def test_transition_probabilities_must_sum_to_one_exactly(self):
        class Bad(TwoStepRuntime):
            def transition_support(self, state, action_id):
                primitive = {p.action_id:p for p in declarations().primitives}[action_id]
                nxt = state.append(action_id=action_id, output_digest="x", kind=primitive.kind, budget_name=primitive.budget_name, cost=primitive.cost)
                return (Transition(Decimal("0.9"), nxt),)
        with self.assertRaisesRegex(ValueError, "SUM_TO_ONE"):
            ExactFiniteSupportBellmanEngine(declarations(), Bad()).solve()

    def test_transition_cannot_skip_budget_accounting(self):
        class Bad(TwoStepRuntime):
            def transition_support(self, state, action_id):
                nxt = ControlState(state.history+((action_id,"x"),), state.compute_remaining, state.acquisition_remaining, state.selection_remaining)
                return (Transition(Decimal("1"), nxt),)
        with self.assertRaisesRegex(ValueError, "BUDGET_OR_RECORD_MISMATCH"):
            ExactFiniteSupportBellmanEngine(declarations(), Bad()).solve()

    def test_undeclared_action_is_rejected(self):
        class Bad(TwoStepRuntime):
            def admissible_actions(self, state):
                return ("not_declared",)
        with self.assertRaisesRegex(ValueError, "UNDECLARED_ACTION"):
            ExactFiniteSupportBellmanEngine(declarations(), Bad()).solve()

    def test_runtime_api_cannot_accept_audit_log(self):
        class Bad(TwoStepRuntime):
            def transition_support(self, state, action_id, audit_log=None):
                return ()
        with self.assertRaisesRegex(ValueError, "SIGNATURE_INVALID|AUDIT_ARGUMENT_FORBIDDEN"):
            ExactFiniteSupportBellmanEngine(declarations(), Bad())

    def test_unfrozen_declaration_bundle_is_rejected(self):
        draft = DeclarationBundle(
            primitives=(PrimitiveSpec("stop",ActionKind.STOP,0.0,"selection",RandomnessOwnership.NONE_DETERMINISTIC),),
            compute_budget=0, acquisition_budget=0, selection_budget=0,
            gamma_theta_id="UNSET_GAMMA", phi_id="UNSET_PHI", delta_stop_id="UNSET_STOP", bellman_policy_id="UNSET_BELLMAN",
        )
        with self.assertRaisesRegex(RuntimeError, "DECLARATIONS_NOT_FROZEN"):
            ExactFiniteSupportBellmanEngine(draft, TwoStepRuntime())

    def test_terminal_risk_and_action_are_validated(self):
        class BadRisk(TwoStepRuntime):
            def terminal_evaluation(self, state):
                return TerminalEvaluation("NO_EDGE", Decimal("1.1"))
        with self.assertRaisesRegex(ValueError, "RISK_OUT_OF_RANGE"):
            ExactFiniteSupportBellmanEngine(declarations(), BadRisk()).solve()


if __name__ == "__main__":
    unittest.main()
