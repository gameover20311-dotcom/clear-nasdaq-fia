from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvidenceRecord:
    evidence_id: str
    category: str
    instrument: str
    source: str
    provider: str
    observed_at: Optional[str]
    first_seen_at: Optional[str]
    freshness: str
    status: str
    raw_value: Any = None
    normalized_value: Optional[float] = None
    quality: float = 0.0
    latency_seconds: Optional[float] = None
    revision: Optional[str] = None
    url: Optional[str] = None
    request_id: Optional[str] = None
    checksum: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SpecialistView:
    name: str
    family: str
    direction: str
    score: float
    probability_bullish: float
    reliability: float
    uncertainty: float
    evidence_ids: List[str] = field(default_factory=list)
    reason: str = ""
    missing_reason: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RegimeView:
    primary: str
    secondary: List[str]
    confidence: float
    reasons: List[str]
    risk_state: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnalogyView:
    available: bool
    horizon: str
    bullish_probability: Optional[float]
    sample_size: int
    effective_sample_size: float
    mean_similarity: float
    nearest: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CriticView:
    severity: str
    score: float
    objections: List[str]
    reinvestigate: List[str]
    correlated_groups: List[str]
    reliability_penalty: float
    hard_hold: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
