from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from umse_master.contracts import DataClass, QualityState
from umse_master.events import EventType, MarketEvent
from umse_master.impact import ImpactContext, compute_response_surprise, estimate_impact_decay
from umse_master.liquidity import BookLevel, OrderBookSnapshot, estimate_liquidity_field

UTC = timezone.utc
T = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)


def ev(idx, typ, size, minute=-1, order_id=None, data_class=DataClass.REAL_L2_DEPTH):
    return MarketEvent(
        typ, T + timedelta(minutes=minute), T + timedelta(minutes=minute), T + timedelta(minutes=minute, seconds=1),
        "test", "NQ", data_class, QualityState.FRESH, f"e{idx}", 20000.0, size, None, order_id, False
    )


class LiquidityImpactTests(unittest.TestCase):
    def book(self, data_class=DataClass.REAL_L2_DEPTH):
        return OrderBookSnapshot(
            T - timedelta(seconds=2), T - timedelta(seconds=1), "test", "NQ", data_class,
            QualityState.FRESH, "book-1",
            bids=(BookLevel(19999.75, 10), BookLevel(19999.50, 20), BookLevel(19999.25, 30)),
            asks=(BookLevel(20000.25, 8), BookLevel(20000.50, 12), BookLevel(20000.75, 16)),
            tick_size=0.25,
        )

    def test_liquidity_field_is_bounded_and_descriptive(self):
        events = [ev(1, EventType.REPLENISH_BID, 8), ev(2, EventType.CANCEL_ASK, 2)]
        f = estimate_liquidity_field(self.book(), T, events)
        self.assertGreater(f.bid_depth, f.ask_depth)
        self.assertGreater(f.depth_imbalance, 0)
        self.assertGreater(f.replenishment_pressure, f.cancellation_pressure)
        self.assertFalse(f.calibrated)
        self.assertFalse(f.exact_queue_metrics_identifiable)

    def test_future_book_rejected(self):
        b = OrderBookSnapshot(
            T + timedelta(minutes=1), T + timedelta(minutes=1), "test", "NQ", DataClass.REAL_L2_DEPTH,
            QualityState.FRESH, "future",
            bids=(BookLevel(19999.75, 1),), asks=(BookLevel(20000.25, 1),)
        )
        with self.assertRaises(ValueError):
            estimate_liquidity_field(b, T)

    def test_impact_surprise_detects_failed_response(self):
        ctx = ImpactContext(100.0, 50.0, 0.1, 0.2)
        strong_expected = compute_response_surprise(0.0, ctx)
        aligned = compute_response_surprise(2.0, ctx)
        self.assertGreater(strong_expected.failed_response_score, 0)
        self.assertTrue(aligned.direction_consistent)
        self.assertFalse(aligned.calibrated)

    def test_impact_decay(self):
        d = estimate_impact_decay([8, 4, 2, 1])
        self.assertTrue(d.identifiable)
        self.assertAlmostEqual(d.half_life_steps, 1.0, places=5)
        self.assertGreater(d.recovery_fraction, 0.8)


if __name__ == "__main__":
    unittest.main()
