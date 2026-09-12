from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Optional

from umse_master.contracts import DataClass, QualityState


class Side(str, Enum):
    BID = "BID"
    ASK = "ASK"


class MBOAction(str, Enum):
    ADD = "ADD"
    MODIFY = "MODIFY"
    CANCEL = "CANCEL"
    TRADE = "TRADE"


class EvidenceStatus(str, Enum):
    OBSERVED = "OBSERVED"
    DEGRADED = "DEGRADED"
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    PROTOCOL_INELIGIBLE = "PROTOCOL_INELIGIBLE"
    UNCALIBRATED = "UNCALIBRATED"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class MBORecord:
    event_time_utc: datetime
    available_time_utc: datetime
    ingested_time_utc: datetime
    source: str
    instrument: str
    data_class: DataClass
    quality_state: QualityState
    provenance_id: str
    sequence: int
    order_id: str
    action: MBOAction
    side: Side
    price: float
    size: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time_utc", _utc(self.event_time_utc))
        object.__setattr__(self, "available_time_utc", _utc(self.available_time_utc))
        object.__setattr__(self, "ingested_time_utc", _utc(self.ingested_time_utc))
        for name in ("source", "instrument", "provenance_id", "order_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.data_class not in {DataClass.REAL_LIVE_MBO, DataClass.REAL_HISTORICAL_MBO}:
            raise ValueError("MBORecord requires a genuine MBO data class")
        if int(self.sequence) < 0:
            raise ValueError("sequence must be >= 0")
        if not math.isfinite(float(self.price)) or float(self.price) <= 0:
            raise ValueError("price must be finite and > 0")
        if not math.isfinite(float(self.size)) or float(self.size) < 0:
            raise ValueError("size must be finite and >= 0")
        if self.action == MBOAction.ADD and self.size <= 0:
            raise ValueError("ADD requires positive size")

    def eligible_at(self, decision_time_utc: datetime, *, max_age_seconds: Optional[float] = None) -> bool:
        decision = _utc(decision_time_utc)
        if self.available_time_utc > decision or self.event_time_utc > decision:
            return False
        if self.quality_state in {QualityState.STALE, QualityState.MISSING, QualityState.INELIGIBLE, QualityState.PROXY}:
            return False
        if max_age_seconds is not None:
            if max_age_seconds < 0:
                raise ValueError("max_age_seconds must be >= 0")
            age = (decision - self.event_time_utc).total_seconds()
            if age > max_age_seconds:
                return False
        return True


@dataclass(frozen=True)
class QueueSurvivalObservation:
    order_id: str
    side: Side
    price: float
    entered_time_utc: datetime
    observed_until_utc: datetime
    lifetime_seconds: float
    initial_size: float
    terminal_remaining_size: float
    terminal_action: Optional[MBOAction]
    censored: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "entered_time_utc", _utc(self.entered_time_utc))
        object.__setattr__(self, "observed_until_utc", _utc(self.observed_until_utc))
        if self.lifetime_seconds < 0:
            raise ValueError("lifetime_seconds must be >= 0")
        if self.initial_size <= 0:
            raise ValueError("initial_size must be > 0")
        if self.terminal_remaining_size < 0:
            raise ValueError("terminal_remaining_size must be >= 0")


@dataclass(frozen=True)
class QueueSurvivalReport:
    status: EvidenceStatus
    observations: tuple[QueueSurvivalObservation, ...]
    exact_order_identity: bool
    sequence_complete: bool
    lineage_complete: bool
    trader_identity_inferred: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.trader_identity_inferred:
            raise ValueError("order identity must never be promoted to trader identity")
        if self.status == EvidenceStatus.OBSERVED and not (
            self.exact_order_identity and self.sequence_complete and self.lineage_complete
        ):
            raise ValueError("OBSERVED queue survival requires complete exact MBO lineage")
