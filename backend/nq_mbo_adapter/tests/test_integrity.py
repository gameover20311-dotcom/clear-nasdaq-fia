from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from nq_mbo_adapter.integrity import IntegrityStatus, SequenceContract, StreamIntegrityGate
from nq_mbo_adapter.types import EventAction, FeedCapability, MBOEvent, Side, SourceCapabilities

NOW = datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc)


def capabilities():
    return SourceCapabilities(
        provider="RITHMIC",
        claimed_capability=FeedCapability.TRUE_MBO,
        individual_order_identity=True,
        sequence_semantics=True,
        add_modify_cancel_semantics=True,
        exchange_timestamps=True,
        historical_replay=True,
    )


def seq_contract(step=1):
    return SequenceContract("TEST_VENDOR_SEQUENCE_V1", lambda token: int(token), step)


def event(seq="100", *, contract="NQZ6", exchange_time=NOW, receive_time=None, action=EventAction.ADD, order_id=None, replay=False):
    return MBOEvent(
        instrument="NQ",
        contract=contract,
        venue="CME",
        source="RITHMIC",
        capability=FeedCapability.TRUE_MBO,
        exchange_timestamp=exchange_time,
        receive_timestamp=receive_time or exchange_time + timedelta(milliseconds=1),
        sequence_id=str(seq),
        order_id=order_id or f"ORDER-{seq}",
        side=Side.BID,
        price=Decimal("25000.25"),
        quantity=1,
        action=action,
        raw_source_hash="a" * 64,
        replay=replay,
    )


class StreamIntegrityGateTests(unittest.TestCase):
    def test_true_mbo_gate_is_not_ready_without_sequence_contract(self):
        gate = StreamIntegrityGate(capabilities=capabilities(), expected_contract="NQZ6")
        self.assertFalse(gate.ready_for_true_mbo)
        r = gate.ingest(event(), now=NOW + timedelta(seconds=1))
        self.assertEqual(r.status, IntegrityStatus.FAIL)
        self.assertEqual(r.reason, "SEQUENCE_CONTRACT_NOT_BOUND")

    def test_valid_contiguous_stream_passes(self):
        gate = StreamIntegrityGate(capabilities=capabilities(), expected_contract="NQZ6", sequence_contract=seq_contract())
        self.assertEqual(gate.ingest(event("100"), now=NOW + timedelta(seconds=1)).status, IntegrityStatus.PASS)
        self.assertEqual(gate.ingest(event("101", exchange_time=NOW+timedelta(milliseconds=2)), now=NOW + timedelta(seconds=1)).status, IntegrityStatus.PASS)

    def test_duplicate_sequence_fails_closed(self):
        gate = StreamIntegrityGate(capabilities=capabilities(), expected_contract="NQZ6", sequence_contract=seq_contract())
        gate.ingest(event("100"), now=NOW + timedelta(seconds=1))
        r = gate.ingest(event("100", exchange_time=NOW+timedelta(milliseconds=2), order_id="OTHER"), now=NOW + timedelta(seconds=1))
        self.assertEqual(r.status, IntegrityStatus.FAIL)
        self.assertEqual(r.reason, "DUPLICATE_SEQUENCE_ID")

    def test_sequence_gap_fails_only_under_declared_sequence_contract(self):
        gate = StreamIntegrityGate(capabilities=capabilities(), expected_contract="NQZ6", sequence_contract=seq_contract(step=1))
        gate.ingest(event("100"), now=NOW + timedelta(seconds=1))
        r = gate.ingest(event("102", exchange_time=NOW+timedelta(milliseconds=2)), now=NOW + timedelta(seconds=1))
        self.assertEqual(r.status, IntegrityStatus.FAIL)
        self.assertEqual(r.reason, "SEQUENCE_GAP_OR_OUT_OF_ORDER")

    def test_exchange_timestamp_reversal_fails(self):
        gate = StreamIntegrityGate(capabilities=capabilities(), expected_contract="NQZ6", sequence_contract=seq_contract())
        gate.ingest(event("100", exchange_time=NOW+timedelta(milliseconds=2)), now=NOW + timedelta(seconds=1))
        r = gate.ingest(event("101", exchange_time=NOW), now=NOW + timedelta(seconds=1))
        self.assertEqual(r.status, IntegrityStatus.FAIL)
        self.assertEqual(r.reason, "EXCHANGE_TIMESTAMP_REVERSAL")

    def test_wrong_contract_fails(self):
        gate = StreamIntegrityGate(capabilities=capabilities(), expected_contract="NQZ6", sequence_contract=seq_contract())
        r = gate.ingest(event(contract="NQH7"), now=NOW + timedelta(seconds=1))
        self.assertEqual(r.status, IntegrityStatus.FAIL)
        self.assertEqual(r.reason, "WRONG_CONTRACT")

    def test_stale_live_event_fails_but_replay_uses_separate_semantics(self):
        gate = StreamIntegrityGate(capabilities=capabilities(), expected_contract="NQZ6", sequence_contract=seq_contract(), max_receive_age_seconds=2)
        stale = event("100", receive_time=NOW)
        r = gate.ingest(stale, now=NOW + timedelta(seconds=10))
        self.assertEqual(r.status, IntegrityStatus.FAIL)
        self.assertEqual(r.reason, "STALE_EVENT")

        replay_gate = StreamIntegrityGate(capabilities=capabilities(), expected_contract="NQZ6", sequence_contract=seq_contract(), max_receive_age_seconds=2)
        replay = event("100", receive_time=NOW, replay=True)
        self.assertEqual(replay_gate.ingest(replay, now=NOW+timedelta(seconds=10)).status, IntegrityStatus.PASS)

    def test_reset_clears_continuity_but_not_duplicate_event_hash_memory(self):
        gate = StreamIntegrityGate(capabilities=capabilities(), expected_contract="NQZ6", sequence_contract=seq_contract())
        first = event("100")
        self.assertEqual(gate.ingest(first, now=NOW+timedelta(seconds=1)).status, IntegrityStatus.PASS)
        reset = event("500", exchange_time=NOW+timedelta(milliseconds=2), action=EventAction.RESET, order_id="RESET")
        self.assertEqual(gate.ingest(reset, now=NOW+timedelta(seconds=1)).status, IntegrityStatus.RESET_ACCEPTED)
        after = event("900", exchange_time=NOW+timedelta(milliseconds=3))
        self.assertEqual(gate.ingest(after, now=NOW+timedelta(seconds=1)).status, IntegrityStatus.PASS)
        duplicate = gate.ingest(first, now=NOW+timedelta(seconds=1))
        self.assertEqual(duplicate.status, IntegrityStatus.FAIL)
        self.assertEqual(duplicate.reason, "DUPLICATE_EVENT_HASH")


if __name__ == "__main__":
    unittest.main()
