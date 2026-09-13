from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Iterable, Optional, Tuple

from .contracts import DataClass, QualityState


class EventType(str, Enum):
    BUY_AGGRESSION = "BUY_AGGRESSION"
    SELL_AGGRESSION = "SELL_AGGRESSION"
    CANCEL_BID = "CANCEL_BID"
    CANCEL_ASK = "CANCEL_ASK"
    REPLENISH_BID = "REPLENISH_BID"
    REPLENISH_ASK = "REPLENISH_ASK"
    SWEEP_BUY = "SWEEP_BUY"
    SWEEP_SELL = "SWEEP_SELL"
    LARGE_TRADE_BUY = "LARGE_TRADE_BUY"
    LARGE_TRADE_SELL = "LARGE_TRADE_SELL"
    BOOK_SNAPSHOT = "BOOK_SNAPSHOT"
    CROSS_MARKET_SHOCK = "CROSS_MARKET_SHOCK"


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class MarketEvent:
    event_type: EventType
    event_time_utc: datetime
    available_time_utc: datetime
    ingested_time_utc: datetime
    source: str
    instrument: str
    data_class: DataClass
    quality_state: QualityState
    provenance_id: str
    price: Optional[float] = None
    size: Optional[float] = None
    level: Optional[int] = None
    order_id: Optional[str] = None
    is_proxy: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time_utc", _utc(self.event_time_utc))
        object.__setattr__(self, "available_time_utc", _utc(self.available_time_utc))
        object.__setattr__(self, "ingested_time_utc", _utc(self.ingested_time_utc))
        for name in ("source", "instrument", "provenance_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.price is not None and not math.isfinite(float(self.price)):
            raise ValueError("price must be finite when present")
        if self.size is not None and (not math.isfinite(float(self.size)) or float(self.size) < 0):
            raise ValueError("size must be finite and >= 0 when present")
        if self.level is not None and int(self.level) < 0:
            raise ValueError("level must be >= 0")
        if self.data_class == DataClass.PROXY_RESEARCH and not self.is_proxy:
            raise ValueError("PROXY_RESEARCH must set is_proxy=True")
        if self.order_id and self.data_class not in {
            DataClass.REAL_LIVE_MBO,
            DataClass.REAL_HISTORICAL_MBO,
        }:
            raise ValueError("order_id is only valid for MBO data classes")

    def age_seconds(self, decision_time_utc: datetime) -> float:
        return max(0.0, (_utc(decision_time_utc) - self.event_time_utc).total_seconds())

    def eligible_at(
        self, decision_time_utc: datetime, *, max_age_seconds: float | None = None
    ) -> bool:
        """See CausalObservation.eligible_at for why max_age_seconds has no default."""
        decision = _utc(decision_time_utc)
        if self.available_time_utc > decision:
            return False
        if max_age_seconds is not None and self.age_seconds(decision) > float(max_age_seconds):
            return False
        return self.quality_state not in {
            QualityState.STALE,
            QualityState.MISSING,
            QualityState.INELIGIBLE,
        }

    @property
    def has_true_order_identity(self) -> bool:
        return bool(self.order_id) and self.data_class in {
            DataClass.REAL_LIVE_MBO,
            DataClass.REAL_HISTORICAL_MBO,
        }


class EventWindow:
    """Immutable causal event collection.

    Filtering uses `available_time_utc`, never later knowledge of event outcome.
    """

    def __init__(self, events: Iterable[MarketEvent] = ()) -> None:
        rows = tuple(events)
        ids = [r.provenance_id for r in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate provenance_id in event window")
        self._events = tuple(
            sorted(rows, key=lambda x: (x.available_time_utc, x.event_time_utc, x.provenance_id))
        )

    @property
    def events(self) -> Tuple[MarketEvent, ...]:
        return self._events

    def causal_slice(
        self,
        decision_time_utc: datetime,
        start_time_utc: Optional[datetime] = None,
        *,
        max_age_seconds: float | None = None,
    ) -> Tuple[MarketEvent, ...]:
        decision = _utc(decision_time_utc)
        start = _utc(start_time_utc) if start_time_utc else None
        out = []
        for row in self._events:
            if not row.eligible_at(decision, max_age_seconds=max_age_seconds):
                continue
            if start is not None and row.event_time_utc < start:
                continue
            if row.event_time_utc > decision:
                # Event time itself is future even if a malformed provider says available.
                continue
            out.append(row)
        return tuple(out)
