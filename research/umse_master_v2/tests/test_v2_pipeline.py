from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from umse_master.contracts import DataClass, QualityState
from umse_master.liquidity import BookLevel, OrderBookSnapshot
from umse_master_v2.contracts import EvidenceStatus, MBOAction, MBORecord, Side
from umse_master_v2.information_velocity import TimedShock
from umse_master_v2.pipeline import V2PipelineConfig, run_v2_shadow
from umse_master_v2.resistance_field import ResistanceConfig


UTC = timezone.utc
T0 = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def mbo(seq: int, action: MBOAction, oid: str, *, second: float, size: float, side: Side = Side.BID) -> MBORecord:
    t = T0 + timedelta(seconds=second)
    return MBORecord(
        event_time_utc=t,
        available_time_utc=t,
        ingested_time_utc=t,
        source="CME",
        instrument="NQ",
        data_class=DataClass.REAL_HISTORICAL_MBO,
        quality_state=QualityState.FRESH,
        provenance_id=f"mbo-{seq}-{oid}-{action.value}",
        sequence=seq,
        order_id=oid,
        action=action,
        side=side,
        price=20000.0 if side == Side.BID else 20000.25,
        size=size,
    )


def book(second: float, bid: float, ask: float) -> OrderBookSnapshot:
    t = T0 + timedelta(seconds=second)
    return OrderBookSnapshot(
        event_time_utc=t,
        available_time_utc=t,
        source="CME",
        instrument="NQ",
        data_class=DataClass.REAL_L2_DEPTH,
        quality_state=QualityState.FRESH,
        provenance_id=f"book-{second}",
        bids=(BookLevel(20000.0, bid), BookLevel(19999.75, bid * 0.8)),
        asks=(BookLevel(20000.25, ask), BookLevel(20000.50, ask * 0.8)),
    )


def config() -> V2PipelineConfig:
    return V2PipelineConfig(
        sequence_domain_complete=True,
        resistance=ResistanceConfig(1.0, 1.0, 1.0),
        source_node="ES",
        target_node="NQ",
        max_lead_lag_seconds=2.0,
        info_minimum_pairs=5,
        leadlag_minimum_events_per_node=20,
        leadlag_permutations=199,
        leadlag_alpha=0.01,
        queue_hazard_minimum_orders=3,
        transport_target_horizon_seconds=4 * 3600.0,
        transport_minimum_survival_weight=0.01,
    )


class V2PipelineTests(unittest.TestCase):
    def test_pipeline_is_fail_closed_with_empty_inputs(self):
        run = run_v2_shadow(
            decision_time_utc=T0 + timedelta(seconds=100),
            mbo_records=(),
            book_snapshots=(),
            shocks=(),
            config=config(),
        )
        self.assertEqual(run.queue_survival.status, EvidenceStatus.INSUFFICIENT_DATA)
        self.assertIsNone(run.queue_lifetime)
        self.assertEqual(run.orderbook_memory.status, EvidenceStatus.INSUFFICIENT_DATA)
        self.assertEqual(run.resistance_field.status, EvidenceStatus.INSUFFICIENT_DATA)
        self.assertEqual(run.information_velocity.status, EvidenceStatus.INSUFFICIENT_DATA)
        self.assertEqual(run.leadlag_evidence.status, EvidenceStatus.INSUFFICIENT_DATA)
        self.assertFalse(run.cross_scale_transport.transport_eligible)
        self.assertFalse(run.predictive_mapping_frozen)
        self.assertFalse(run.predictive_edge_proven)
        self.assertFalse(run.production_effect)

    def test_pipeline_reaches_every_implemented_live_component(self):
        records = []
        seq = 100
        # Three complete queue lifetimes plus extra provision/depletion flow.
        for i in range(3):
            oid = f"o{i}"
            records.append(mbo(seq, MBOAction.ADD, oid, second=i * 3, size=5.0))
            seq += 1
            records.append(mbo(seq, MBOAction.CANCEL, oid, second=i * 3 + 1, size=5.0))
            seq += 1

        books = [
            book(i, 100 + 15 * ((i % 4) - 1), 100 - 10 * ((i % 3) - 1))
            for i in range(12)
        ]

        shocks = []
        elapsed = 0.0
        for i in range(24):
            elapsed += 7.0 + float((i * 11) % 13)
            s = T0 + timedelta(seconds=elapsed)
            t = s + timedelta(seconds=0.25)
            shocks.append(TimedShock("ES", s, s, f"es-{i}", float((i % 5) - 2)))
            shocks.append(TimedShock("NQ", t, t, f"nq-{i}", float((i % 5) - 2)))

        decision = T0 + timedelta(seconds=500)
        run = run_v2_shadow(
            decision_time_utc=decision,
            mbo_records=records,
            book_snapshots=books,
            shocks=shocks,
            config=config(),
        )

        self.assertEqual(run.queue_survival.status, EvidenceStatus.OBSERVED)
        self.assertIsNotNone(run.queue_lifetime)
        self.assertEqual(run.resistance_field.status, EvidenceStatus.UNCALIBRATED)
        self.assertEqual(run.information_velocity.status, EvidenceStatus.UNCALIBRATED)
        self.assertEqual(run.leadlag_evidence.status, EvidenceStatus.UNCALIBRATED)
        self.assertTrue(run.evidence_hash)
        self.assertEqual(len(run.evidence_hash), 64)
        self.assertFalse(run.production_effect)
        self.assertFalse(run.predictive_edge_proven)

    def test_evidence_hash_is_deterministic_and_changes_with_input_provenance(self):
        c = config()
        shock = TimedShock("ES", T0, T0, "s1", 1.0)
        target = TimedShock("NQ", T0 + timedelta(seconds=1), T0 + timedelta(seconds=1), "t1", 1.0)
        decision = T0 + timedelta(seconds=100)
        a = run_v2_shadow(
            decision_time_utc=decision,
            mbo_records=(),
            book_snapshots=(),
            shocks=(shock, target),
            config=c,
        )
        b = run_v2_shadow(
            decision_time_utc=decision,
            mbo_records=(),
            book_snapshots=(),
            shocks=(shock, target),
            config=c,
        )
        self.assertEqual(a.evidence_hash, b.evidence_hash)

        changed = TimedShock("NQ", target.event_time_utc, target.available_time_utc, "t2", 1.0)
        d = run_v2_shadow(
            decision_time_utc=decision,
            mbo_records=(),
            book_snapshots=(),
            shocks=(shock, changed),
            config=c,
        )
        self.assertNotEqual(a.evidence_hash, d.evidence_hash)


if __name__ == "__main__":
    unittest.main()
