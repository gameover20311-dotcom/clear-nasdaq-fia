from __future__ import annotations

import unittest

from mfre_v125_shadow.types import ActionKind, ControlState, PrimitiveSpec, RandomnessOwnership


class MFREBudgetInvariantTests(unittest.TestCase):
    def test_non_stop_zero_cost_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least one budget unit"):
            PrimitiveSpec("bad", ActionKind.COMPUTE, 0.0, "compute", RandomnessOwnership.ENGINE_OWNED)

    def test_stop_must_be_zero_cost(self):
        with self.assertRaisesRegex(ValueError, "zero resource cost"):
            PrimitiveSpec("stop", ActionKind.STOP, 1.0, "selection", RandomnessOwnership.NONE_DETERMINISTIC)

    def test_budget_name_is_declared_domain(self):
        with self.assertRaisesRegex(ValueError, "compute/acquisition/selection"):
            PrimitiveSpec("bad", ActionKind.COMPUTE, 1.0, "mystery", RandomnessOwnership.ENGINE_OWNED)

    def test_declared_cost_decrements_matching_budget(self):
        state = ControlState((), 5.0, 4.0, 3.0)
        next_state = state.append(action_id="compute", output_digest="x", kind=ActionKind.COMPUTE, budget_name="compute", cost=2.0)
        self.assertEqual(next_state.compute_remaining, 3.0)
        self.assertEqual(next_state.acquisition_remaining, 4.0)
        self.assertEqual(next_state.selection_remaining, 3.0)

    def test_selection_budget_is_real_not_dead_state(self):
        state = ControlState((), 5.0, 4.0, 3.0)
        next_state = state.append(action_id="select_countermodel", output_digest="x", kind=ActionKind.COMPUTE, budget_name="selection", cost=1.0)
        self.assertEqual(next_state.selection_remaining, 2.0)
        self.assertEqual(next_state.compute_remaining, 5.0)

    def test_unaffordable_action_fails_closed(self):
        state = ControlState((), 0.0, 0.0, 0.0)
        with self.assertRaisesRegex(RuntimeError, "SELECTION_BUDGET_EXHAUSTED"):
            state.append(action_id="select", output_digest="x", kind=ActionKind.COMPUTE, budget_name="selection", cost=1.0)


if __name__ == "__main__":
    unittest.main()
