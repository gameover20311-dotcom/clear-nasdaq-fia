from __future__ import annotations

"""Rithmic integration boundary.

This deliberately does NOT invent transport fields, protobuf schemas, endpoints,
or entitlements before the exact vendor/API contract is supplied. Credentials
must be injected at runtime and must never be committed or echoed.
"""

from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator

from .provider import AdapterHealth, MarketDataAdapter
from .types import FeedCapability, MBOEvent, SourceCapabilities


class RithmicAdapterStatus(str, Enum):
    AWAITING_VENDOR_CONTRACT = "AWAITING_VENDOR_CONTRACT"
    AWAITING_CREDENTIALS = "AWAITING_CREDENTIALS"
    DISCONNECTED = "DISCONNECTED"
    CONNECTED_UNVERIFIED_CAPABILITY = "CONNECTED_UNVERIFIED_CAPABILITY"
    CONNECTED_TRUE_MBO_VERIFIED = "CONNECTED_TRUE_MBO_VERIFIED"


@dataclass(frozen=True)
class RithmicConnectionSpec:
    """Non-secret binding metadata only.

    `contract_id` fingerprints the exact vendor protocol/schema/entitlement
    contract after it is reviewed. Secret credentials are intentionally absent.
    """

    contract_id: str | None = None
    environment: str | None = None
    credentials_available: bool = False


class RithmicAdapter(MarketDataAdapter):
    def __init__(self, spec: RithmicConnectionSpec | None = None):
        self._spec = spec or RithmicConnectionSpec()
        self._connected = False
        self._verified_capabilities: SourceCapabilities | None = None

    def bind_verified_capabilities(self, capabilities: SourceCapabilities) -> None:
        if capabilities.provider.upper() != "RITHMIC":
            raise ValueError("RITHMIC_PROVIDER_ID_REQUIRED")
        self._verified_capabilities = capabilities

    async def connect(self) -> None:
        if not self._spec.contract_id:
            raise RuntimeError("RITHMIC_VENDOR_CONTRACT_NOT_BOUND")
        if not self._spec.credentials_available:
            raise RuntimeError("RITHMIC_CREDENTIALS_NOT_AVAILABLE")
        # Real transport implementation is intentionally blocked until the exact
        # vendor contract is supplied and audited.
        raise RuntimeError("RITHMIC_TRANSPORT_IMPLEMENTATION_NOT_BOUND")

    async def disconnect(self) -> None:
        self._connected = False

    async def subscribe(self, contract: str) -> None:
        if not self._connected:
            raise RuntimeError("RITHMIC_NOT_CONNECTED")
        if not contract.strip():
            raise ValueError("CONTRACT_REQUIRED")
        raise RuntimeError("RITHMIC_SUBSCRIPTION_IMPLEMENTATION_NOT_BOUND")

    async def events(self) -> AsyncIterator[MBOEvent]:
        if not self._connected:
            raise RuntimeError("RITHMIC_NOT_CONNECTED")
        if False:
            yield  # pragma: no cover
        return

    def capabilities(self) -> SourceCapabilities:
        if self._verified_capabilities is not None:
            return self._verified_capabilities
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
        elif not self._spec.credentials_available:
            status = RithmicAdapterStatus.AWAITING_CREDENTIALS.value
        elif not self._connected:
            status = RithmicAdapterStatus.DISCONNECTED.value
        elif self.capabilities().verified_true_mbo:
            status = RithmicAdapterStatus.CONNECTED_TRUE_MBO_VERIFIED.value
        else:
            status = RithmicAdapterStatus.CONNECTED_UNVERIFIED_CAPABILITY.value
        return AdapterHealth(
            provider="RITHMIC",
            connected=self._connected,
            status=status,
            capability=self.capabilities().claimed_capability.value,
            detail="No market-data capability is escalated without a verified vendor contract.",
        )
