from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

from .types import MBOEvent, SourceCapabilities


@dataclass(frozen=True)
class AdapterHealth:
    provider: str
    connected: bool
    status: str
    capability: str
    last_sequence_id: str | None = None
    detail: str | None = None


class MarketDataAdapter(ABC):
    """Read-only market-data transport boundary. No order-entry methods exist."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def subscribe(self, contract: str) -> None: ...

    @abstractmethod
    async def events(self) -> AsyncIterator[MBOEvent]: ...

    @abstractmethod
    def capabilities(self) -> SourceCapabilities: ...

    @abstractmethod
    def health(self) -> AdapterHealth: ...
