from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from umse_master.contracts import CausalObservation, DataClass, QualityState, ShadowStatus
from umse_master.cross_scale import Scale, ScaleEvidence
from umse_master.events import EventType, MarketEvent
from umse_master.hawkes import HawkesNetworkConfig
from umse_master.liquidity import BookLevel, OrderBookSnapshot
from umse_master.pipeline import run_umse_shadow

UTC = timezone.utc
T = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)


class FullShadowPipelineTests(unittest.TestCase):
    def test_full_research_pipeline_remains_fail_closed(self):
        obs = [
            CausalObservation(T-timedelta(minutes=2), T-timedelta(minutes=2), T-timedelta(minutes=2), "test", "NQ", DataClass.REAL_TRADES_QUOTES, QualityState.FRESH, False, "o1", 1.0)
        ]
        events = [
            MarketEvent(EventType.BUY_AGGRESSION, T-timedelta(minutes=4), T-timedelta(minutes=4), T-timedelta(minutes=4), "test", "NQ", DataClass.REAL_L2_DEPTH, QualityState.FRESH, "e1", 20000, 10),
            MarketEvent(EventType.SELL_AGGRESSION, T-timedelta(minutes=3), T-timedelta(minutes=3), T-timedelta(minutes=3), "test", "NQ", DataClass.REAL_L2_DEPTH, QualityState.FRESH, "e2", 20000.5, 4),
            MarketEvent(EventType.REPLENISH_BID, T-timedelta(minutes=2), T-timedelta(minutes=2), T-timedelta(minutes=2), "test", "NQ", DataClass.REAL_L2_DEPTH, QualityState.FRESH, "e3", 20001, 8),
            MarketEvent(EventType.CANCEL_ASK, T-timedelta(minutes=1), T-timedelta(minutes=1), T-timedelta(minutes=1), "test", "NQ", DataClass.REAL_L2_DEPTH, QualityState.FRESH, "e4", 20001.25, 2),
        ]
        book = OrderBookSnapshot(
            T-timedelta(seconds=10), T-timedelta(seconds=9), "test", "NQ", DataClass.REAL_L2_DEPTH,
            QualityState.FRESH, "book", (BookLevel(19999.75, 20), BookLevel(19999.5, 15)),
            (BookLevel(20000.25, 10), BookLevel(20000.5, 12)), .25
        )
        hcfg = HawkesNetworkConfig(
            (EventType.BUY_AGGRESSION, EventType.SELL_AGGRESSION), (.1, .1),
            ((.2, .05), (.05, .2)), ((1.0, 1.0), (1.0, 1.0))
        )
        scale = [ScaleEvidence(Scale.MICRO, T, .7, .9, 600), ScaleEvidence(Scale.MESO, T, .6, .8, 600)]
        result = run_umse_shadow(
            observations=obs, events=events, decision_time_utc=T, book=book, hawkes_config=hcfg,
            realized_volatility=.2, recovery_responses=[1, .7, .4, .2], state_series=[.1, .2, .3, .4],
            scale_evidence=scale,
        )
        self.assertEqual(result.snapshot.status, ShadowStatus.NO_UMSE_EDGE)
        self.assertFalse(result.snapshot.production_effect)
        self.assertFalse(result.diagnostics.production_effect)
        self.assertFalse(result.diagnostics.predictive_mapping_frozen)
        self.assertIsNotNone(result.diagnostics.liquidity)
        self.assertIsNotNone(result.diagnostics.response_surprise)
        self.assertIsNotNone(result.diagnostics.hawkes)
        self.assertEqual(len(result.diagnostics.evidence_hash), 64)
        horizons = sorted(x.horizon_hours for x in result.snapshot.estimates)
        self.assertEqual(horizons, [4, 8])
        for estimate in result.snapshot.estimates:
            self.assertEqual(estimate.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
