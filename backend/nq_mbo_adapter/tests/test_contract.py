from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from nq_mbo_adapter.rithmic import RithmicAdapter, RithmicAdapterStatus, RithmicConnectionSpec
from nq_mbo_adapter.types import EventAction, FeedCapability, MBOEvent, Side, SourceCapabilities
from nq_mbo_adapter.validation import MBOValidationError, validate_capability_claim, validate_event


NOW = datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc)


def caps(capability=FeedCapability.TRUE_MBO, *, order_id=True, sequence=True, lifecycle=True, timestamps=True, replay=True):
    return SourceCapabilities(
        provider="RITHMIC",
        claimed_capability=capability,
        individual_order_identity=order_id,
        sequence_semantics=sequence,
        add_modify_cancel_semantics=lifecycle,
        exchange_timestamps=timestamps,
        historical_replay=replay,
    )


def event(**overrides):
    base = dict(
        instrument="NQ", contract="NQZ6", venue="CME", source="RITHMIC",
        capability=FeedCapability.TRUE_MBO,
        exchange_timestamp=NOW,
        receive_timestamp=NOW + timedelta(milliseconds=1),
        sequence_id="1001", order_id="ORDER-1", side=Side.BID,
        price=Decimal("25000.25"), quantity=3, action=EventAction.ADD,
        raw_source_hash="a"*64, replay=False,
    )
    base.update(overrides)
    return MBOEvent(**base)


class NQMBOContractTests(unittest.TestCase):
    def test_true_mbo_claim_requires_order_identity_and_sequence_semantics(self):
        with self.assertRaisesRegex(MBOValidationError, "TRUE_MBO_CLAIM_NOT_PROVEN"):
            validate_capability_claim(caps(order_id=False))
        with self.assertRaisesRegex(MBOValidationError, "TRUE_MBO_CLAIM_NOT_PROVEN"):
            validate_capability_claim(caps(sequence=False))

    def test_true_mbo_event_requires_real_order_id_and_sequence(self):
        with self.assertRaisesRegex(MBOValidationError, "ORDER_ID_REQUIRED"):
            validate_event(event(order_id=None), caps())
        with self.assertRaisesRegex(MBOValidationError, "SEQUENCE_ID_REQUIRED"):
            validate_event(event(sequence_id=None), caps())

    def test_no_synthetic_id_fallback_exists(self):
        e = event(order_id=None, capability=FeedCapability.MBP_DEPTH)
        validate_event(e, caps(FeedCapability.MBP_DEPTH, order_id=False, sequence=False, lifecycle=False, timestamps=True))
        self.assertIsNone(e.order_id)
        self.assertIsNone(e.canonical_payload()["order_id"])

    def test_receive_time_cannot_precede_exchange_time(self):
        with self.assertRaisesRegex(MBOValidationError, "RECEIVE_TIME_PRECEDES"):
            validate_event(event(receive_timestamp=NOW-timedelta(milliseconds=1)), caps())

    def test_replay_is_not_accepted_if_source_does_not_declare_it(self):
        with self.assertRaisesRegex(MBOValidationError, "HISTORICAL_REPLAY"):
            validate_event(event(replay=True), caps(replay=False))

    def test_rithmic_starts_fail_closed_without_vendor_contract(self):
        adapter = RithmicAdapter()
        self.assertEqual(adapter.health().status, RithmicAdapterStatus.AWAITING_VENDOR_CONTRACT.value)
        self.assertEqual(adapter.health().capability, FeedCapability.L1_ONLY.value)
        with self.assertRaisesRegex(RuntimeError, "VENDOR_CONTRACT_NOT_BOUND"):
            asyncio.run(adapter.connect())

    def test_contract_without_credentials_remains_disconnected(self):
        adapter = RithmicAdapter(RithmicConnectionSpec(contract_id="sha256:vendor-contract", environment="test", credentials_available=False))
        self.assertEqual(adapter.health().status, RithmicAdapterStatus.AWAITING_CREDENTIALS.value)
        with self.assertRaisesRegex(RuntimeError, "CREDENTIALS_NOT_AVAILABLE"):
            asyncio.run(adapter.connect())

    def test_verified_capability_does_not_connect_transport_by_itself(self):
        adapter = RithmicAdapter(RithmicConnectionSpec(contract_id="sha256:vendor-contract", environment="test", credentials_available=True))
        adapter.bind_verified_capabilities(caps())
        self.assertTrue(adapter.capabilities().verified_true_mbo)
        self.assertFalse(adapter.health().connected)
        with self.assertRaisesRegex(RuntimeError, "TRANSPORT_IMPLEMENTATION_NOT_BOUND"):
            asyncio.run(adapter.connect())


if __name__ == "__main__":
    unittest.main()
