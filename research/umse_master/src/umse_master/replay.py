from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Iterator, Sequence, Tuple

from .events import EventWindow, MarketEvent


class ReplayClass(str, Enum):
    DEBUG = "DEBUG"
    CALIBRATION = "CALIBRATION"
    UNTOUCHED_HISTORICAL_TEST = "UNTOUCHED_HISTORICAL_TEST"
    FORWARD_OOS = "FORWARD_OOS"


@dataclass(frozen=True)
class ReplayDecision:
    decision_time_utc: datetime
    events: Tuple[MarketEvent, ...]
    replay_class: ReplayClass
    prospective_proof: bool

    def __post_init__(self) -> None:
        if self.decision_time_utc.tzinfo is None:
            raise ValueError("decision_time_utc must be timezone-aware")
        if self.replay_class != ReplayClass.FORWARD_OOS and self.prospective_proof:
            raise ValueError("historical replay cannot be marked as prospective proof")


class CausalReplay:
    def __init__(self, events: Iterable[MarketEvent]) -> None:
        self.window = EventWindow(events)

    def decisions(
        self,
        decision_times_utc: Sequence[datetime],
        *,
        replay_class: ReplayClass,
    ) -> Iterator[ReplayDecision]:
        previous = None
        for decision in decision_times_utc:
            if decision.tzinfo is None:
                raise ValueError("decision times must be timezone-aware")
            d = decision.astimezone(timezone.utc)
            if previous is not None and d <= previous:
                raise ValueError("decision times must be strictly increasing")
            previous = d
            rows = self.window.causal_slice(d)
            yield ReplayDecision(
                decision_time_utc=d,
                events=rows,
                replay_class=replay_class,
                prospective_proof=(replay_class == ReplayClass.FORWARD_OOS),
            )
