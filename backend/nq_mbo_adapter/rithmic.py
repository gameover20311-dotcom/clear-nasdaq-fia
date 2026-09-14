from __future__ import annotations

"""Read-only Rithmic Protocol market-data adapter.

The transport is deliberately limited to the ticker plant.  No order, PnL, or
history plant is connected and this module exposes no order-entry operation.
Credentials are resolved only from environment variables at runtime and are
never stored in the connection spec, logs, health output, or event payloads.

Rithmic Protocol 0.89.0.0 DepthByOrder carries a provider sequence number plus
batched NEW/CHANGE/DELETE mutations, exchange order ids, side, price, size and
source timestamps.  Capability remains fail-closed until those primitives are
actually observed on the credentialed live/test stream.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import os
import re
import sys
from typing import Any, AsyncIterator

from .provider import AdapterHealth, MarketDataAdapter
from .types import EventAction, FeedCapability, MBOEvent, Side, SourceCapabilities
from .validation import MBOValidationError, validate_event


_CONTRACT_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROTOCOL_VERSION = "0.89.0.0"
_DEFAULT_TEST_URL = "rituz00100.rithmic.com:443"
_DEFAULT_TEST_SYSTEM = "Rithmic Test"


class RithmicAdapterStatus(str, Enum):
    AWAITING_VENDOR_CONTRACT = "AWAITING_VENDOR_CONTRACT"
    AWAITING_CREDENTIALS = "AWAITING_CREDENTIALS"
    DISCONNECTED = "DISCONNECTED"
    CONNECTED_UNVERIFIED_CAPABILITY = "CONNECTED_UNVERIFIED_CAPABILITY"
    CONNECTED_MBP_DEPTH_VERIFIED = "CONNECTED_MBP_DEPTH_VERIFIED"
    CONNECTED_TRUE_MBO_VERIFIED = "CONNECTED_TRUE_MBO_VERIFIED"


@dataclass(frozen=True)
class RithmicConnectionSpec:
    """Non-secret transport binding metadata.

    `contract_id` is the SHA-256 of the exact vendor dev-kit archive reviewed by
    the project, formatted as ``sha256:<64 lowercase hex>``.  Secret credentials
    are intentionally absent and are read only from `username_env` and
    `password_env` during connect().
    """

    contract_id: str | None = None
    protocol_version: str = _PROTOCOL_VERSION
    environment: str = "test"
    credentials_available: bool = False
    url: str = _DEFAULT_TEST_URL
    system_name: str = _DEFAULT_TEST_SYSTEM
    app_name: str = "CLEAR_NASDAQ_FIA"
    app_version: str = "1.0"
    exchange: str = "CME"
    username_env: str = "RITHMIC_USER"
    password_env: str = "RITHMIC_PASSWORD"
    max_depth_price_subscriptions: int = 40

    def __post_init__(self) -> None:
        if self.contract_id is not None and not _CONTRACT_SHA.fullmatch(self.contract_id):
            raise ValueError("RITHMIC_CONTRACT_ID_MUST_BE_SHA256")
        if self.protocol_version != _PROTOCOL_VERSION:
            raise ValueError("RITHMIC_PROTOCOL_VERSION_NOT_AUDITED")
        if self.environment.lower() != "test":
            raise ValueError("RITHMIC_ADAPTER_TEST_ENVIRONMENT_ONLY")
        if self.url != _DEFAULT_TEST_URL:
            raise ValueError("RITHMIC_TEST_URL_NOT_AUDITED")
        if self.system_name != _DEFAULT_TEST_SYSTEM:
            raise ValueError("RITHMIC_TEST_SYSTEM_NAME_NOT_AUDITED")
        if self.exchange != "CME":
            raise ValueError("RITHMIC_NQ_EXCHANGE_MUST_BE_CME")
        if self.max_depth_price_subscriptions <= 0:
            raise ValueError("MAX_DEPTH_PRICE_SUBSCRIPTIONS_MUST_BE_POSITIVE")


class RithmicAdapter(MarketDataAdapter):
    def __init__(self, spec: RithmicConnectionSpec | None = None):
        self._spec = spec or RithmicConnectionSpec()
        self._connected = False
        self._client: Any | None = None
        self._verified_capabilities: SourceCapabilities | None = None
        self._observed_mbp = False
        self._subscribed_contract: str | None = None
        self._depth_prices: set[float] = set()
        self._event_queue: asyncio.Queue[MBOEvent | None] = asyncio.Queue()
        self._last_sequence_id: str | None = None
        self._last_error: str | None = None

    def bind_verified_capabilities(self, capabilities: SourceCapabilities) -> None:
        if capabilities.provider.upper() != "RITHMIC":
            raise ValueError("RITHMIC_PROVIDER_ID_REQUIRED")
        self._verified_capabilities = capabilities

    def _credentials_present(self) -> bool:
        return bool(os.environ.get(self._spec.username_env) and os.environ.get(self._spec.password_env))

    async def connect(self) -> None:
        if not self._spec.contract_id:
            raise RuntimeError("RITHMIC_VENDOR_CONTRACT_NOT_BOUND")
        if not self._spec.credentials_available or not self._credentials_present():
            raise RuntimeError("RITHMIC_CREDENTIALS_NOT_AVAILABLE")
        if sys.version_info < (3, 10):
            raise RuntimeError("RITHMIC_TRANSPORT_REQUIRES_PYTHON_3_10_PLUS")
        if self._connected:
            return

        try:
            from async_rithmic import RithmicClient, SysInfraType
        except Exception as exc:  # pragma: no cover - exercised by deployment/runtime
            raise RuntimeError("RITHMIC_TRANSPORT_DEPENDENCY_UNAVAILABLE") from exc

        # Secrets are consumed here and never retained separately by this adapter.
        self._client = RithmicClient(
            user=os.environ[self._spec.username_env],
            password=os.environ[self._spec.password_env],
            system_name=self._spec.system_name,
            app_name=self._spec.app_name,
            app_version=self._spec.app_version,
            url=self._spec.url,
        )
        self._client.on_order_book += self._on_order_book
        self._client.on_market_depth += self._on_market_depth

        try:
            # Hard safety boundary: ticker plant only.  No order-routing plant.
            await self._client.connect(plants=[SysInfraType.TICKER_PLANT])
        except Exception:
            self._client = None
            raise
        self._connected = True
        self._last_error = None

    async def disconnect(self) -> None:
        client = self._client
        self._connected = False
        if client is not None:
            try:
                if self._subscribed_contract:
                    try:
                        from async_rithmic import DataType
                        await client.unsubscribe_from_market_data(
                            self._subscribed_contract, self._spec.exchange, DataType.ORDER_BOOK
                        )
                    except Exception:
                        pass
                    for price in tuple(self._depth_prices):
                        try:
                            await client.unsubscribe_from_market_depth(
                                self._subscribed_contract, self._spec.exchange, price
                            )
                        except Exception:
                            pass
                await client.disconnect()
            finally:
                self._client = None
                self._subscribed_contract = None
                self._depth_prices.clear()
        await self._event_queue.put(None)

    async def subscribe(self, contract: str) -> None:
        if not self._connected or self._client is None:
            raise RuntimeError("RITHMIC_NOT_CONNECTED")
        contract = contract.strip().upper()
        if not contract:
            raise ValueError("CONTRACT_REQUIRED")
        if contract == "NQ":
            contract = (await self._client.get_front_month_contract("NQ", self._spec.exchange)).upper()
        if not contract.startswith("NQ"):
            raise ValueError("RITHMIC_ADAPTER_NQ_ONLY")
        if self._subscribed_contract and self._subscribed_contract != contract:
            raise RuntimeError("RITHMIC_SINGLE_CONTRACT_SUBSCRIPTION_ONLY")

        from async_rithmic import DataType

        self._subscribed_contract = contract
        await self._client.subscribe_to_market_data(contract, self._spec.exchange, DataType.ORDER_BOOK)

    async def events(self) -> AsyncIterator[MBOEvent]:
        if not self._connected:
            raise RuntimeError("RITHMIC_NOT_CONNECTED")
        while True:
            item = await self._event_queue.get()
            if item is None:
                return
            yield item

    def capabilities(self) -> SourceCapabilities:
        if self._verified_capabilities is not None:
            return self._verified_capabilities
        if self._observed_mbp:
            return SourceCapabilities(
                provider="RITHMIC",
                claimed_capability=FeedCapability.MBP_DEPTH,
                individual_order_identity=False,
                sequence_semantics=False,
                add_modify_cancel_semantics=False,
                exchange_timestamps=True,
                historical_replay=False,
                raw_redistribution_authorized=False,
            )
        return SourceCapabilities(
            provider="RITHMIC",
            claimed_capability=FeedCapability.L1_ONLY,
            individual_order_identity=False,
            sequence_semantics=False,
            add_modify_cancel_semantics=False,
            exchange_timestamps=False,
            historical_replay=False,
            raw_redistribution_authorized=False,
        )

    def health(self) -> AdapterHealth:
        if not self._spec.contract_id:
            status = RithmicAdapterStatus.AWAITING_VENDOR_CONTRACT.value
        elif not self._spec.credentials_available or not self._credentials_present():
            status = RithmicAdapterStatus.AWAITING_CREDENTIALS.value
        elif not self._connected:
            status = RithmicAdapterStatus.DISCONNECTED.value
        elif self.capabilities().verified_true_mbo:
            status = RithmicAdapterStatus.CONNECTED_TRUE_MBO_VERIFIED.value
        elif self._observed_mbp:
            status = RithmicAdapterStatus.CONNECTED_MBP_DEPTH_VERIFIED.value
        else:
            status = RithmicAdapterStatus.CONNECTED_UNVERIFIED_CAPABILITY.value

        detail = (
            f"protocol={self._spec.protocol_version}; environment=test; ticker_plant_only; "
            f"depth_price_subscriptions={len(self._depth_prices)}/{self._spec.max_depth_price_subscriptions}; "
            "TRUE_MBO requires credentialed DepthByOrder evidence; no order-routing authority."
        )
        if self._last_error:
            detail += f" last_error={self._last_error}"
        return AdapterHealth(
            provider="RITHMIC",
            connected=self._connected,
            status=status,
            capability=self.capabilities().claimed_capability.value,
            last_sequence_id=self._last_sequence_id,
            detail=detail,
        )

    async def _on_order_book(self, response: Any) -> None:
        """Observe L2 and bind price-scoped DepthByOrder subscriptions.

        Rithmic's DepthByOrder subscription is price-scoped.  We therefore use
        the ordinary order-book stream only as a discovery surface for visible
        NQ price levels, then subscribe to DepthByOrder updates for a bounded set
        of nearest prices.  This does not claim complete full-book coverage.
        """
        if not self._connected or self._client is None or not self._subscribed_contract:
            return
        if str(getattr(response, "symbol", "")).upper() != self._subscribed_contract:
            self._last_error = "ORDER_BOOK_WRONG_CONTRACT"
            return
        if str(getattr(response, "exchange", "")).upper() != self._spec.exchange:
            self._last_error = "ORDER_BOOK_WRONG_EXCHANGE"
            return

        bids = [float(x) for x in getattr(response, "bid_price", ()) if float(x) > 0]
        asks = [float(x) for x in getattr(response, "ask_price", ()) if float(x) > 0]
        self._observed_mbp = bool(bids or asks)
        prices = set(bids + asks)
        if not prices:
            return

        if bids and asks:
            midpoint = (max(bids) + min(asks)) / 2.0
        elif bids:
            midpoint = max(bids)
        else:
            midpoint = min(asks)
        ordered = sorted(prices, key=lambda p: (abs(p - midpoint), p))

        for price in ordered:
            if price in self._depth_prices:
                continue
            if len(self._depth_prices) >= self._spec.max_depth_price_subscriptions:
                break
            try:
                await self._client.subscribe_to_market_depth(
                    self._subscribed_contract, self._spec.exchange, price
                )
            except Exception as exc:
                self._last_error = f"DEPTH_SUBSCRIBE_FAILED:{type(exc).__name__}"
                return
            self._depth_prices.add(price)

    @staticmethod
    def _source_timestamp(response: Any) -> datetime | None:
        ssboe = int(getattr(response, "source_ssboe", 0) or 0)
        if ssboe <= 0:
            return None
        usecs = int(getattr(response, "source_usecs", 0) or 0)
        nsecs = int(getattr(response, "source_nsecs", 0) or 0)
        # Rithmic supplies source timestamp precision according to the upstream
        # source. Prefer nanoseconds when present; otherwise use microseconds.
        micros = nsecs // 1000 if nsecs > 0 else usecs
        return datetime.fromtimestamp(ssboe, tz=timezone.utc) + timedelta(microseconds=micros)

    @staticmethod
    def _raw_hash(response: Any) -> str:
        try:
            raw = response.SerializeToString(deterministic=True)
        except TypeError:  # older protobuf runtime
            raw = response.SerializeToString()
        return hashlib.sha256(raw).hexdigest()

    async def _on_market_depth(self, response: Any) -> None:
        """Translate credentialed Rithmic DepthByOrder template-160 batches."""
        if not self._connected or not self._subscribed_contract:
            return
        symbol = str(getattr(response, "symbol", "")).upper()
        exchange = str(getattr(response, "exchange", "")).upper()
        if symbol != self._subscribed_contract or exchange != self._spec.exchange:
            self._last_error = "DEPTH_BY_ORDER_SCOPE_MISMATCH"
            return

        # Rithmic Protocol 0.89.0.0 declares this field as uint64 but does not
        # declare a positive-only constraint.  Zero is therefore a valid wire
        # value and was observed on the credentialed Rithmic Test stream.  The
        # old `<= 0` check incorrectly conflated a valid zero with a missing
        # field.  We still fail closed when the field itself is unavailable,
        # non-integral, or outside the uint64 domain.
        if not hasattr(response, "sequence_number"):
            self._last_error = "DEPTH_BY_ORDER_SEQUENCE_MISSING"
            return
        try:
            sequence_number = int(response.sequence_number)
        except (TypeError, ValueError, OverflowError):
            self._last_error = "DEPTH_BY_ORDER_SEQUENCE_INVALID"
            return
        if sequence_number < 0 or sequence_number > 0xFFFFFFFFFFFFFFFF:
            self._last_error = "DEPTH_BY_ORDER_SEQUENCE_INVALID"
            return

        exchange_timestamp = self._source_timestamp(response)
        if exchange_timestamp is None:
            self._last_error = "DEPTH_BY_ORDER_SOURCE_TIMESTAMP_MISSING"
            return

        update_types = list(getattr(response, "update_type", ()))
        transaction_types = list(getattr(response, "transaction_type", ()))
        prices = list(getattr(response, "depth_price", ()))
        sizes = list(getattr(response, "depth_size", ()))
        order_ids = list(getattr(response, "exchange_order_id", ()))
        count = len(update_types)
        if count == 0 or any(len(x) != count for x in (transaction_types, prices, sizes, order_ids)):
            self._last_error = "DEPTH_BY_ORDER_BATCH_SHAPE_INVALID"
            return

        action_map = {1: EventAction.ADD, 2: EventAction.MODIFY, 3: EventAction.CANCEL}
        side_map = {1: Side.BID, 2: Side.ASK}
        raw_hash = self._raw_hash(response)
        receive_timestamp = datetime.now(timezone.utc)
        capabilities = SourceCapabilities(
            provider="RITHMIC",
            claimed_capability=FeedCapability.TRUE_MBO,
            individual_order_identity=True,
            sequence_semantics=True,
            add_modify_cancel_semantics=True,
            exchange_timestamps=True,
            historical_replay=False,
            raw_redistribution_authorized=False,
        )

        translated: list[MBOEvent] = []
        for index in range(count):
            action = action_map.get(int(update_types[index]))
            side = side_map.get(int(transaction_types[index]))
            order_id = str(order_ids[index]).strip()
            price = Decimal(str(prices[index])) if float(prices[index]) > 0 else None
            quantity = int(sizes[index]) if int(sizes[index]) > 0 else None
            if action is None or not order_id:
                self._last_error = "DEPTH_BY_ORDER_LIFECYCLE_OR_ORDER_ID_INVALID"
                return
            if action in {EventAction.ADD, EventAction.MODIFY} and (side is None or price is None or quantity is None):
                self._last_error = "DEPTH_BY_ORDER_ADD_MODIFY_FIELDS_INVALID"
                return

            event = MBOEvent(
                instrument="NQ",
                contract=symbol,
                venue=exchange,
                source="RITHMIC",
                capability=FeedCapability.TRUE_MBO,
                exchange_timestamp=exchange_timestamp,
                receive_timestamp=receive_timestamp,
                sequence_id=str(sequence_number),
                sequence_subindex=index,
                order_id=order_id,
                side=side,
                price=price,
                quantity=quantity,
                action=action,
                raw_source_hash=raw_hash,
                replay=False,
            )
            try:
                validate_event(event, capabilities)
            except MBOValidationError as exc:
                self._last_error = f"DEPTH_BY_ORDER_VALIDATION_FAILED:{exc}"
                return
            translated.append(event)

        # Capability escalation occurs only after the entire credentialed batch
        # has been translated and validated successfully.
        self._verified_capabilities = capabilities
        self._last_sequence_id = str(sequence_number)
        self._last_error = None
        for event in translated:
            await self._event_queue.put(event)
