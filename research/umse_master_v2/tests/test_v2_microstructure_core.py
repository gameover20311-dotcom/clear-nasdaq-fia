from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from umse_master.contracts import DataClass, QualityState
from umse_master.liquidity import BookLevel, OrderBookSnapshot
from umse_master_v2.contracts import EvidenceStatus, MBOAction, MBORecord, Side
from umse_master_v2.information_velocity import TimedShock, estimate_information_velocity
from umse_master_v2.orderbook_memory import estimate_orderbook_memory
from umse_master_v2.queue_survival import reconstruct_queue_survival
from umse_master_v2.resistance_field import ResistanceConfig, estimate_resistance_field


UTC = timezone.utc
T0 = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def mbo(seq: int, action: MBOAction, order_id: str = "o1", *, side: Side = Side.BID, size: float = 5.0,
        seconds: int | None = None, available_offset: float = 0.0, source: str = "CME") -> MBORecord:
    sec = seq if seconds is None else seconds
    event = T0 + timedelta(seconds=sec)
    return MBORecord(
        event_time_utc=event,
        available_time_utc=event + timedelta(seconds=available_offset),
        ingested_time_utc=event + timedelta(seconds=max(0.0, available_offset)),
        source=source,
        instrument="NQ",
        data_class=DataClass.REAL_HISTORICAL_MBO,
        quality_state=QualityState.FRESH,
        provenance_id=f"{source}-{seq}-{action.value}-{order_id}",
        sequence=seq,
        order_id=order_id,
        action=action,
        side=side,
        price=20000.0 if side == Side.BID else 20000.25,
        size=size,
    )


def book(second: int, bid_size: float, ask_size: float) -> OrderBookSnapshot:
    event = T0 + timedelta(seconds=second)
    return OrderBookSnapshot(
        event_time_utc=event,
        available_time_utc=event,
        source="CME",
        instrument="NQ",
        data_class=DataClass.REAL_L2_DEPTH,
        quality_state=QualityState.FRESH,
        provenance_id=f"book-{second}-{bid_size}-{ask_size}",
        bids=(BookLevel(20000.0, bid_size), BookLevel(19999.75, max(1.0, bid_size * 0.8))),
        asks=(BookLevel(20000.25, ask_size), BookLevel(20000.50, max(1.0, ask_size * 0.8))),
    )


class MBOTruthContractTests(unittest.TestCase):
    def test_l2_cannot_masquerade_as_mbo(self):
        with self.assertRaises(ValueError):
            MBORecord(
                event_time_utc=T0,
                available_time_utc=T0,
                ingested_time_utc=T0,
                source="x",
                instrument="NQ",
                data_class=DataClass.REAL_L2_DEPTH,
                quality_state=QualityState.FRESH,
                provenance_id="p",
                sequence=1,
                order_id="o",
                action=MBOAction.ADD,
                side=Side.BID,
                price=20000,
                size=1,
            )

    def test_future_availability_is_ineligible(self):
        row = mbo(1, MBOAction.ADD, available_offset=10.0)
        self.assertFalse(row.eligible_at(T0 + timedelta(seconds=5)))

    def test_exact_queue_survival_requires_complete_lineage(self):
        rows = [
            mbo(10, MBOAction.ADD, size=5, seconds=0),
            mbo(11, MBOAction.TRADE, size=2, seconds=1),
            mbo(12, MBOAction.CANCEL, size=3, seconds=2),
        ]
        result = reconstruct_queue_survival(rows, T0 + timedelta(seconds=3))
        self.assertEqual(result.status, EvidenceStatus.OBSERVED)
        self.assertTrue(result.sequence_complete)
        self.assertTrue(result.lineage_complete)
        self.assertFalse(result.trader_identity_inferred)
        self.assertEqual(len(result.observations), 1)
        self.assertAlmostEqual(result.observations[0].lifetime_seconds, 2.0)
        self.assertFalse(result.observations[0].censored)

    def test_sequence_gap_degrades_exact_claim(self):
        rows = [mbo(10, MBOAction.ADD, seconds=0), mbo(12, MBOAction.CANCEL, seconds=1)]
        result = reconstruct_queue_survival(rows, T0 + timedelta(seconds=2))
        self.assertEqual(result.status, EvidenceStatus.DEGRADED)
        self.assertFalse(result.sequence_complete)
        self.assertIn("SEQUENCE_GAP", result.reasons)

    def test_missing_add_lineage_degrades(self):
        result = reconstruct_queue_survival([mbo(5, MBOAction.TRADE, size=1)], T0 + timedelta(seconds=10))
        self.assertEqual(result.status, EvidenceStatus.DEGRADED)
        self.assertFalse(result.lineage_complete)
        self.assertTrue(any(x.startswith("MISSING_ADD_LINEAGE") for x in result.reasons))

    def test_mixed_sequence_spaces_fail_protocol(self):
        rows = [mbo(1, MBOAction.ADD, source="A"), mbo(2, MBOAction.ADD, order_id="o2", source="B")]
        result = reconstruct_queue_survival(rows, T0 + timedelta(seconds=10))
        self.assertEqual(result.status, EvidenceStatus.PROTOCOL_INELIGIBLE)


class OrderBookMemoryTests(unittest.TestCase):
    def test_small_sample_refuses_memory_claim(self):
        result = estimate_orderbook_memory([book(i, 10 + i, 10) for i in range(5)], T0 + timedelta(seconds=10))
        self.assertEqual(result.status, EvidenceStatus.INSUFFICIENT_DATA)

    def test_irregular_sampling_refuses_step_to_seconds_conversion(self):
        times = [0, 1, 2, 20, 21, 40, 41, 60]
        snaps = [book(t, 10 + (i % 3) * 5, 20 - (i % 2) * 4) for i, t in enumerate(times)]
        result = estimate_orderbook_memory(snaps, T0 + timedelta(seconds=100), max_interval_cv=0.2)
        self.assertEqual(result.status, EvidenceStatus.DEGRADED)
        self.assertIsNone(result.approximate_half_life_seconds)
        self.assertIn("IRREGULAR_SNAPSHOT_INTERVALS_STEP_TO_TIME_CONVERSION_REFUSED", result.reasons)


class ResistanceFieldTests(unittest.TestCase):
    def test_requested_missing_flow_is_not_silently_zero(self):
        snapshot = book(0, 100, 100)
        config = ResistanceConfig(depth_weight=1, provision_weight=1, depletion_weight=1)
        result = estimate_resistance_field(snapshot, [], T0 + timedelta(seconds=2), config)
        self.assertEqual(result.status, EvidenceStatus.INSUFFICIENT_DATA)
        self.assertIsNone(result.bid_resistance)

    def test_field_remains_uncalibrated_with_real_mbo(self):
        snapshot = book(0, 120, 80)
        records = [
            mbo(1, MBOAction.ADD, "b1", side=Side.BID, size=10),
            mbo(2, MBOAction.ADD, "a1", side=Side.ASK, size=4),
            mbo(3, MBOAction.CANCEL, "b2", side=Side.BID, size=3),
            mbo(4, MBOAction.TRADE, "a2", side=Side.ASK, size=7),
        ]
        config = ResistanceConfig(depth_weight=1, provision_weight=1, depletion_weight=1)
        result = estimate_resistance_field(snapshot, records, T0 + timedelta(seconds=10), config)
        self.assertEqual(result.status, EvidenceStatus.UNCALIBRATED)
        self.assertFalse(result.calibrated)
        self.assertIsNotNone(result.directional_asymmetry)
        self.assertGreaterEqual(result.bid_resistance, 0.0)
        self.assertLessEqual(result.bid_resistance, 1.0)


class InformationVelocityTests(unittest.TestCase):
    def test_future_unavailable_shock_cannot_enter_matching(self):
        shocks = []
        for i in range(5):
            s = T0 + timedelta(seconds=i * 10)
            shocks.append(TimedShock("ES", s, s, f"s{i}", float(i + 1)))
            target_time = s + timedelta(seconds=2)
            available = target_time if i < 4 else T0 + timedelta(seconds=999)
            shocks.append(TimedShock("NQ", target_time, available, f"t{i}", float(i + 1)))
        result = estimate_information_velocity(
            shocks,
            T0 + timedelta(seconds=100),
            source_node="ES",
            target_node="NQ",
            max_lag_seconds=5,
            minimum_pairs=5,
        )
        self.assertEqual(result.status, EvidenceStatus.INSUFFICIENT_DATA)
        self.assertEqual(result.matched_pairs, 4)
        self.assertFalse(result.directional_claim_allowed)

    def test_descriptive_lead_lag_never_calls_itself_calibrated(self):
        shocks = []
        for i in range(6):
            s = T0 + timedelta(seconds=i * 10)
            t = s + timedelta(seconds=2)
            shocks.append(TimedShock("ES", s, s, f"s{i}", float(i + 1)))
            shocks.append(TimedShock("NQ", t, t, f"t{i}", float(i + 1)))
        result = estimate_information_velocity(
            shocks,
            T0 + timedelta(seconds=100),
            source_node="ES",
            target_node="NQ",
            max_lag_seconds=5,
            minimum_pairs=5,
        )
        self.assertEqual(result.status, EvidenceStatus.UNCALIBRATED)
        self.assertAlmostEqual(result.median_lag_seconds, 2.0)
        self.assertTrue(result.directional_claim_allowed)
        self.assertFalse(result.calibrated)
        self.assertIn("DESCRIPTIVE_LEAD_LAG_REQUIRES_NULL_AND_LATENCY_CONTROL", result.reasons)


if __name__ == "__main__":
    unittest.main()
