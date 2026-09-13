from __future__ import annotations

import unittest

from mfre_v125_shadow.types import ActionKind, DeclarationBundle, PrimitiveSpec, RandomnessOwnership


class MFRETieBreakContractTests(unittest.TestCase):
    def _base(self, tie_break):
        return DeclarationBundle(
            primitives=(
                PrimitiveSpec("stop", ActionKind.STOP, 0.0, "selection", RandomnessOwnership.NONE_DETERMINISTIC),
                PrimitiveSpec("search", ActionKind.COMPUTE, 1.0, "selection", RandomnessOwnership.ENGINE_OWNED),
            ),
            compute_budget=1, acquisition_budget=1, selection_budget=1,
            gamma_theta_id="UNSET_GAMMA", phi_id="UNSET_PHI", delta_stop_id="UNSET_STOP", bellman_policy_id="UNSET_BELLMAN",
            tie_break=tie_break,
        )

    def test_bellman_tie_break_orders_declared_action_ids(self):
        bundle = self._base(("stop", "search"))
        self.assertEqual(bundle.tie_break, ("stop", "search"))

    def test_terminal_labels_are_not_a_bellman_action_order(self):
        with self.assertRaisesRegex(ValueError, "declared primitive action_id"):
            self._base(("Bull", "Bear", "NO_EDGE"))

    def test_partial_or_duplicate_action_order_is_rejected(self):
        with self.assertRaises(ValueError):
            self._base(("stop",))
        with self.assertRaises(ValueError):
            self._base(("stop", "stop"))


if __name__ == "__main__":
    unittest.main()
