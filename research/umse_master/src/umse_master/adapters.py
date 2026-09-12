from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Iterator, Mapping, Sequence, Tuple

from .contracts import DataClass
from .events import MarketEvent


class Capability(str, Enum):
    LIVE = "LIVE"
    HISTORICAL = "HISTORICAL"
    MBO = "MBO"
    L2 = "L2"
    TRADES_QUOTES = "TRADES_QUOTES"
    CROSS_MARKET = "CROSS_MARKET"


@dataclass(frozen=True)
class AdapterDeclaration:
    name: str
    data_class: DataClass
    capabilities: Tuple[Capability, ...]
    raw_redistribution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("adapter name required")
        caps = set(self.capabilities)
        if Capability.MBO in caps and self.data_class not in {
            DataClass.REAL_LIVE_MBO,
            DataClass.REAL_HISTORICAL_MBO,
        }:
            raise ValueError("MBO capability requires an MBO data class")
        if self.data_class in {DataClass.REAL_LIVE_MBO, DataClass.REAL_HISTORICAL_MBO} and Capability.MBO not in caps:
            raise ValueError("MBO data class must declare MBO capability")


class MarketDataAdapter(ABC):
    declaration: AdapterDeclaration

    @abstractmethod
    def iter_events(self) -> Iterable[MarketEvent]:
        raise NotImplementedError


class InMemoryAdapter(MarketDataAdapter):
    def __init__(self, declaration: AdapterDeclaration, events: Sequence[MarketEvent]) -> None:
        self.declaration = declaration
        self._events = tuple(events)
        for event in self._events:
            if event.data_class != declaration.data_class:
                raise ValueError("event data_class does not match adapter declaration")

    def iter_events(self) -> Iterable[MarketEvent]:
        return iter(self._events)
