from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
import sys
import types
import unittest
from unittest.mock import patch

from nq_mbo_adapter.rithmic import RithmicAdapter, RithmicConnectionSpec
from nq_mbo_adapter.types import EventAction, FeedCapability, Side


CONTRACT_ID = "sha256:" + ("b" * 64)


class FakeEventHook:
    def __init__(self):
        self.callbacks = []

    def __iadd__(self, callback):
        self.callbacks.append(callback)
        return self


class FakeClient:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.on_order_book = FakeEventHook()
        self.on_market_depth = FakeEventHook()
        self.connect_plants = None
        self.market_data_subscriptions = []
        self.depth_subscriptions = []
        self.market_data_unsubscriptions = []
        self.depth_unsubscriptions = []
        self.disconnected = False
        FakeClient.instances.append(self)

    async def connect(self, *, plants):
        self.connect_plants = list(plants)

    async def disconnect(self):
        self.disconnected = True

    async def get_front_month_contract(self, symbol, exchange):
        assert symbol == "NQ" and exchange == "CME"
        return "NQZ6"

    async def subscribe_to_market_data(self, symbol, exchange, data_type):
        self.market_data_subscriptions.append((symbol, exchange, data_type))

    async def unsubscribe_from_market_data(self, symbol, exchange, data_type):
        self.market_data_unsubscriptions.append((symbol, exchange, data_type))

    async def subscribe_to_market_depth(self, symbol, exchange, price):
        self.depth_subscriptions.append((symbol, exchange, price))

    async def unsubscribe_from_market_depth(self, symbol, exchange, price):
        self.depth_unsubscriptions.append((symbol, exchange, price))


class FakeOrderBook:
    symbol = "NQZ6"
    exchange = "CME"
    bid_price = [25000.00, 24999.75]
    ask_price = [25000.25, 25000.50]


class FakeDepthByOrder:
    symbol = "NQZ6"
    exchange = "CME"
    sequence_number = 123
    update_type = [1, 2]
    transaction_type = [1, 2]
    depth_price = [25000.00, 25000.25]
    depth_size = [3, 2]
    exchange_order_id = ["ORDER-A", "ORDER-B"]
    source_ssboe = int(datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc).timestamp())
    source_usecs = 123456
    source_nsecs = 0

    def SerializeToString(self, deterministic=False):
        return b"rithmic-depth-by-order-batch-123"


class FakeDepthWithoutSourceTimestamp(FakeDepthByOrder):
    sequence_number = 124
    source_ssboe = 0


class RithmicTransportTests(unittest.TestCase):
    def setUp(self):
        FakeClient.instances.clear()
        module = types.ModuleType("async_rithmic")
        module.RithmicClient = FakeClient
        module.SysInfraType = types.SimpleNamespace(TICKER_PLANT="TICKER_PLANT")
        module.DataType = types.SimpleNamespace(ORDER_BOOK=4)
        self.module_patch = patch.dict(sys.modules, {"async_rithmic": module})
        self.env_patch = patch.dict(os.environ, {"RITHMIC_USER": "test-user", "RITHMIC_PASSWORD": "test-password"}, clear=False)
        self.module_patch.start()
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.module_patch.stop()

    def adapter(self, *, max_prices=40):
        return RithmicAdapter(RithmicConnectionSpec(
            contract_id=CONTRACT_ID,
            credentials_available=True,
            max_depth_price_subscriptions=max_prices,
        ))

    def test_connects_ticker_plant_only_and_does_not_expose_secret_in_health(self):
        async def run():
            adapter = self.adapter()
            await adapter.connect()
            client = FakeClient.instances[-1]
            self.assertEqual(client.connect_plants, ["TICKER_PLANT"])
            health = adapter.health()
            self.assertTrue(health.connected)
            self.assertNotIn("test-user", health.detail or "")
            self.assertNotIn("test-password", health.detail or "")
            await adapter.disconnect()
            self.assertTrue(client.disconnected)
        asyncio.run(run())

    def test_nq_subscription_resolves_front_month_and_binds_depth_prices(self):
        async def run():
            adapter = self.adapter(max_prices=3)
            await adapter.connect()
            await adapter.subscribe("NQ")
            client = FakeClient.instances[-1]
            self.assertEqual(client.market_data_subscriptions, [("NQZ6", "CME", 4)])
            await adapter._on_order_book(FakeOrderBook())
            self.assertEqual(len(client.depth_subscriptions), 3)
            self.assertEqual(adapter.capabilities().claimed_capability, FeedCapability.MBP_DEPTH)
            await adapter.disconnect()
        asyncio.run(run())

    def test_non_nq_contract_is_rejected(self):
        async def run():
            adapter = self.adapter()
            await adapter.connect()
            with self.assertRaisesRegex(ValueError, "NQ_ONLY"):
                await adapter.subscribe("ESZ6")
            await adapter.disconnect()
        asyncio.run(run())

    def test_valid_depth_by_order_batch_escalates_true_mbo_and_preserves_subindices(self):
        async def run():
            adapter = self.adapter()
            await adapter.connect()
            await adapter.subscribe("NQZ6")
            await adapter._on_market_depth(FakeDepthByOrder())

            self.assertTrue(adapter.capabilities().verified_true_mbo)
            self.assertEqual(adapter.health().last_sequence_id, "123")

            stream = adapter.events()
            first = await asyncio.wait_for(stream.__anext__(), timeout=1)
            second = await asyncio.wait_for(stream.__anext__(), timeout=1)
            self.assertEqual((first.sequence_id, first.sequence_subindex), ("123", 0))
            self.assertEqual((second.sequence_id, second.sequence_subindex), ("123", 1))
            self.assertEqual((first.order_id, second.order_id), ("ORDER-A", "ORDER-B"))
            self.assertEqual((first.action, second.action), (EventAction.ADD, EventAction.MODIFY))
            self.assertEqual((first.side, second.side), (Side.BID, Side.ASK))
            self.assertEqual(first.capability, FeedCapability.TRUE_MBO)
            await adapter.disconnect()
        asyncio.run(run())

    def test_missing_source_timestamp_fails_closed_without_capability_escalation(self):
        async def run():
            adapter = self.adapter()
            await adapter.connect()
            await adapter.subscribe("NQZ6")
            await adapter._on_market_depth(FakeDepthWithoutSourceTimestamp())
            self.assertFalse(adapter.capabilities().verified_true_mbo)
            self.assertIn("SOURCE_TIMESTAMP_MISSING", adapter.health().detail or "")
            await adapter.disconnect()
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
