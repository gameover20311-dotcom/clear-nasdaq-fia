from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from umse_master.contracts import DataClass, QualityState
from umse_master.events import EventType, MarketEvent
from umse_master.fusion import ExpertOpinion, reliability_weighted_fusion
from umse_master.geometry import distribution_shift
from umse_master.hawkes import HawkesNetworkConfig, hawkes_diagnostics
from umse_master.information import mutual_information, pid_i_min_approximation, transfer_entropy

UTC = timezone.utc
T = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)


class HawkesInformationTests(unittest.TestCase):
    def event(self, idx, typ):
        return MarketEvent(
            typ, T - timedelta(seconds=idx), T - timedelta(seconds=idx), T - timedelta(seconds=idx-0.1),
            "test", "NQ", DataClass.REAL_TRADES_QUOTES, QualityState.FRESH, f"e{idx}", 20000, 1
        )

    def test_hawkes_integrated_kernel_and_rho(self):
        cfg = HawkesNetworkConfig(
            (EventType.BUY_AGGRESSION, EventType.SELL_AGGRESSION),
            (0.1, 0.1),
            ((0.2, 0.1), (0.05, 0.2)),
            ((1.0, 1.0), (1.0, 1.0)),
        )
        d = hawkes_diagnostics(cfg, [self.event(1, EventType.BUY_AGGRESSION)], T)
        self.assertGreater(d.spectral_radius, 0)
        self.assertLess(d.spectral_radius, 1)
        self.assertTrue(d.subcritical)
        self.assertFalse(d.calibrated)

    def test_information_functions(self):
        x = [0, 0, 1, 1, 0, 0, 1, 1]
        y = list(x)
        self.assertGreater(mutual_information(x, y), 0.9)
        self.assertGreaterEqual(transfer_entropy(x, y), 0.0)
        pid = pid_i_min_approximation(x, y, y)
        self.assertGreaterEqual(pid.redundancy, 0)
        self.assertEqual(pid.method, "I_MIN_STYLE_HEURISTIC_NOT_FULL_PID")

    def test_geometry_identical_distribution_zero_shift(self):
        g = distribution_shift([0.2, 0.3, 0.5], [0.2, 0.3, 0.5])
        self.assertAlmostEqual(g.jensen_shannon, 0.0, places=10)
        self.assertAlmostEqual(g.wasserstein, 0.0, places=10)

    def test_fusion_discounts_redundancy_group(self):
        experts = [
            ExpertOpinion("a", {"bullish": .8, "bearish": .1, "neutral": .1}, 1, 1, "flow"),
            ExpertOpinion("b", {"bullish": .8, "bearish": .1, "neutral": .1}, 1, 1, "flow"),
            ExpertOpinion("c", {"bullish": .2, "bearish": .2, "neutral": .6}, 1, 1, "macro"),
        ]
        r = reliability_weighted_fusion(experts)
        self.assertAlmostEqual(sum(r.probabilities.values()), 1.0, places=9)
        self.assertFalse(r.predictive)
        self.assertLess(r.effective_expert_weight, 3.0)


if __name__ == "__main__":
    unittest.main()
