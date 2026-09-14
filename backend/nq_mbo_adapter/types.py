from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Any, Mapping


class FeedCapability(str, Enum):
    TRUE_MBO = "TRUE_MBO"
    MBP_DEPTH = "MBP_DEPTH"
    L1_ONLY = "L1_ONLY"


class EventAction(str, Enum):
    ADD = "ADD"
    MODIFY = "MODIFY"
    CANCEL = "CANCEL"
    RESET = "RESET"


class Side(str, Enum):
    BID = "BID"
    ASK = "ASK"


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SourceCapabilities:
    provider: str
    claimed_capability: FeedCapability
    individual_order_identity: bool
    sequence_semantics: bool
    add_modify_cancel_semantics: bool
    exchange_timestamps: bool
    historical_replay: bool = False
    raw_redistribution_authorized: bool = False

    @property
    def verified_true_mbo(self) -> bool:
        return (
            self.claimed_capability is FeedCapability.TRUE_MBO
            and self.individual_order_identity
            and self.sequence_semantics
            and self.add_modify_cancel_semantics
            and self.exchange_timestamps
        )


@dataclass(frozen=True)
class MBOEvent:
    instrument: str
    contract: str
    venue: str
    source: str
    capability: FeedCapability
    exchange_timestamp: datetime
    receive_timestamp: datetime
    sequence_id: str | None
    order_id: str | None
    side: Side | None
    price: Decimal | None
    quantity: int | None
    action: EventAction
    # Some providers, including Rithmic Protocol 0.89.0.0 DepthByOrder,
    # attach one provider sequence number to a batch containing multiple order
    # updates.  `sequence_subindex` preserves the exact position within that
    # provider batch without inventing a synthetic provider sequence number.
    sequence_subindex: int | None = None
    depth: int | None = None
    raw_source_hash: str | None = None
    replay: bool = False

    def canonical_payload(self) -> Mapping[str, Any]:
        return {
            "instrument": self.instrument,
            "contract": self.contract,
            "venue": self.venue,
            "source": self.source,
            "capability": self.capability.value,
            "exchange_timestamp": _iso(self.exchange_timestamp),
            "receive_timestamp": _iso(self.receive_timestamp),
            "sequence_id": self.sequence_id,
            "sequence_subindex": self.sequence_subindex,
            "order_id": self.order_id,
            "side": self.side.value if self.side else None,
            "price": str(self.price) if self.price is not None else None,
            "quantity": self.quantity,
            "action": self.action.value,
            "depth": self.depth,
            "raw_source_hash": self.raw_source_hash,
            "replay": self.replay,
        }

    @property
    def event_hash(self) -> str:
        raw = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
