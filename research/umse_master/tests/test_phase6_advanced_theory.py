from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from umse_master.agents import infer_agent_pressure
from umse_master.irreversibility import path_irreversibility
from umse_master.marginal_info import incremental_information, shapley_information
from umse_master.state_space import forward_filter
from umse_master.survival import analyze_state_survival


class AdvancedTheoryTests(unittest.TestCase):
    def test_agent_inference_never_claims_direct_identity(self):
        r = infer_agent_pressure(
            aggression_imbalance=.7, signed_price_response=.5, failed_response_score=.2,
            liquidity_thinness=.4, replenishment_ratio=.6, persistence=.7,
            true_mbo_identity_fraction=1.0,
        )
        self.assertFalse(r.direct_agent_identity_identifiable)
        self.assertFalse(r.predictive)
        self.assertGreater(r.urgency, 0)

    def test_survival_diagnostics(self):
        r = analyze_state_survival([60, 120, 240, 480, 600], target_duration=240)
        self.assertGreaterEqual(r.metastability_score, 0)
        self.assertLessEqual(r.metastability_score, 1)
        self.assertFalse(r.calibrated)

    def test_hmm_filter_is_normalized_and_not_learned(self):
        r = forward_filter(
            states=["A", "B"], prior=[.5, .5], transition=[[.9, .1], [.2, .8]],
            emission_likelihoods=[[.8, .2], [.7, .3]],
        )
        self.assertEqual(len(r.steps), 2)
        self.assertAlmostEqual(sum(r.steps[-1].posterior), 1.0, places=10)
        self.assertFalse(r.learned_parameters)

    def test_path_irreversibility(self):
        r = path_irreversibility(["A", "B", "B", "C", "C", "C"])
        self.assertGreaterEqual(r.forward_reverse_kl, 0)
        self.assertGreater(r.unique_transitions, 0)

    def test_shapley_information_attributes_joint_information(self):
        target = [0, 0, 1, 1, 0, 0, 1, 1]
        features = {
            "x": target,
            "noise": [0, 1, 0, 1, 1, 0, 1, 0],
        }
        r = shapley_information(features, target)
        self.assertGreater(r.shapley_bits["x"], r.shapley_bits["noise"])
        self.assertGreater(r.total_joint_information_bits, 0)
        self.assertGreaterEqual(incremental_information(target, target), .9)


if __name__ == "__main__":
    unittest.main()
