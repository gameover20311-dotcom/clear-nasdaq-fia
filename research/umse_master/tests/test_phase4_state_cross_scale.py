from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from umse_master.complexity import assess_complexity
from umse_master.contracts import Mechanism
from umse_master.criticality import compute_criticality
from umse_master.cross_scale import Scale, ScaleEvidence, assess_cross_scale
from umse_master.hypotheses import MASTER_HYPOTHESES, HypothesisTier
from umse_master.mechanisms import MechanismEvidence, compete_mechanisms
from umse_master.mst import MSTComponents, compute_mst
from umse_master.state import StateEvidence, infer_state

UTC = timezone.utc
T = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)


class StateCrossScaleTests(unittest.TestCase):
    def test_mechanism_competition_and_state_are_normalized(self):
        m = compete_mechanisms(MechanismEvidence(.7, .5, .6, .3, .5, .2, .2, .3))
        self.assertAlmostEqual(sum(m.hypothesis_weights.values()), 1.0, places=9)
        self.assertFalse(m.predictive)
        s = infer_state(StateEvidence(m.hypothesis_weights, .4, .5, .2, .3, .4))
        self.assertAlmostEqual(sum(s.state_weights.values()), 1.0, places=9)
        self.assertFalse(s.predictive)

    def test_cross_scale_requires_survival(self):
        rows = [
            ScaleEvidence(Scale.MICRO, T, .8, .9, 600),
            ScaleEvidence(Scale.MESO, T, .7, .9, 600),
            ScaleEvidence(Scale.SESSION, T, .6, .9, 600),
        ]
        r = assess_cross_scale(rows)
        self.assertTrue(r.allow_4h_influence)
        self.assertTrue(r.allow_8h_influence)
        self.assertGreater(r.survival_to_4h, r.survival_to_8h)
        self.assertFalse(r.calibrated)

    def test_criticality_and_mst_are_candidate_only(self):
        c = compute_criticality(
            hawkes_spectral_radius=.7,
            state_series=[0.1, .2, .3, .35, .4],
            recovery_responses=[1, .8, .6, .4, .2],
            price_change=2,
            liquidity_change=10,
        )
        self.assertGreaterEqual(c.candidate_index, 0)
        self.assertLessEqual(c.candidate_index, 1)
        m = compute_mst(MSTComponents(.7, c.candidate_index, .6, .5, .7, .3, .2, .4, .1))
        self.assertGreaterEqual(m.original_concept_value, 0)
        self.assertLessEqual(m.original_concept_value, 1)
        self.assertFalse(m.predictive)

    def test_complexity_and_hypothesis_registry(self):
        a = assess_complexity(5, 100)
        self.assertTrue(a.adequate_sample_ratio)
        self.assertGreater(a.bic_penalty, 0)
        names = {h.name for h in MASTER_HYPOTHESES}
        self.assertIn("inverse_game_or_irl", names)
        self.assertTrue(any(h.tier == HypothesisTier.SPECULATIVE for h in MASTER_HYPOTHESES))


if __name__ == "__main__":
    unittest.main()
