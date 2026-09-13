from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from umse_master.contracts import DataClass, QualityState
from umse_master.events import EventType, EventWindow, MarketEvent
from umse_master.primitives import compute_primitives

UTC = timezone.utc
T = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)


def event(
    idx: int,
    event_type: EventType,
    *,
    minutes: int = -1,
    available_minutes: int | None = None,
    size: float = 1.0,
    price: float | None = 20000.0,
    data_class: DataClass = DataClass.REAL_L2_DEPTH,
    quality: QualityState = QualityState.FRESH,
    order_id: str | None = None,
) -> MarketEvent:
    available_minutes = minutes if available_minutes is None else available_minutes
    return MarketEvent(
        event_type=event_type,
        event_time_utc=T + timedelta(minutes=minutes),
        available_time_utc=T + timedelta(minutes=available_minutes),
        ingested_time_utc=T + timedelta(minutes=available_minutes, seconds=1),
        source="test",
        instrument="NQ",
        data_class=data_class,
        quality_state=quality,
        provenance_id=f"e{idx}",
        price=price,
        size=size,
        order_id=order_id,
    )


class EventKernelTests(unittest.TestCase):
    def test_future_event_time_is_excluded_even_if_available_time_is_malformed(self):
        future = event(1, EventType.BUY_AGGRESSION, minutes=1, available_minutes=-1)
        rows = EventWindow([future]).causal_slice(T)
        self.assertEqual(rows, ())

    def test_future_available_event_is_excluded(self):
        row = event(1, EventType.BUY_AGGRESSION, minutes=-1, available_minutes=1)
        self.assertEqual(EventWindow([row]).causal_slice(T), ())

    def test_duplicate_provenance_fails_closed(self):
        a = event(1, EventType.BUY_AGGRESSION)
        with self.assertRaises(ValueError):
            EventWindow([a, a])

    def test_order_identity_rejected_for_non_mbo(self):
        with self.assertRaises(ValueError):
            event(1, EventType.BOOK_SNAPSHOT, order_id="abc")

    def test_primitives_are_descriptive_and_causal(self):
        rows = [
            event(1, EventType.BUY_AGGRESSION, minutes=-4, size=10, price=20000),
            event(2, EventType.SELL_AGGRESSION, minutes=-3, size=4, price=20001),
            event(3, EventType.REPLENISH_BID, minutes=-2, size=6, price=20002),
            event(4, EventType.CANCEL_BID, minutes=-1, size=2, price=20003),
            event(5, EventType.BUY_AGGRESSION, minutes=1, available_minutes=1, size=999, price=21000),
        ]
        p = compute_primitives(EventWindow(rows), T)
        self.assertEqual(p.event_count, 4)
        self.assertEqual(p.buy_aggressive_volume, 10)
        self.assertEqual(p.sell_aggressive_volume, 4)
        self.assertEqual(p.signed_aggressive_volume, 6)
        self.assertAlmostEqual(p.aggression_imbalance, 6 / 14)
        self.assertEqual(p.replenishment_volume, 6)
        self.assertEqual(p.cancellation_volume, 2)
        self.assertAlmostEqual(p.replenishment_ratio, 0.75)
        self.assertEqual(p.observed_price_change, 3)
        self.assertFalse(p.queue_survival_identifiable)

    def test_queue_survival_requires_true_mbo_identity_for_every_event(self):
        rows = [
            event(
                1,
                EventType.BUY_AGGRESSION,
                data_class=DataClass.REAL_HISTORICAL_MBO,
                order_id="o1",
            ),
            event(
                2,
                EventType.CANCEL_BID,
                data_class=DataClass.REAL_HISTORICAL_MBO,
                order_id="o2",
            ),
        ]
        p = compute_primitives(EventWindow(rows), T)
        self.assertTrue(p.queue_survival_identifiable)
        self.assertEqual(p.true_mbo_order_identity_fraction, 1.0)


if __name__ == "__main__":
    unittest.main()
