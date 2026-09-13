from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Dict, Mapping, Optional, Tuple


class DataClass(str, Enum):
    REAL_LIVE_MBO = "REAL_LIVE_MBO"
    REAL_HISTORICAL_MBO = "REAL_HISTORICAL_MBO"
    REAL_L2_DEPTH = "REAL_L2_DEPTH"
    REAL_TRADES_QUOTES = "REAL_TRADES_QUOTES"
    REAL_CROSS_MARKET = "REAL_CROSS_MARKET"
    PROXY_RESEARCH = "PROXY_RESEARCH"
    SYNTHETIC_TEST = "SYNTHETIC_TEST"


class QualityState(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    DEGRADED = "DEGRADED"
    PROXY = "PROXY"
    INELIGIBLE = "INELIGIBLE"


class ShadowStatus(str, Enum):
    SHADOW_ESTIMATE = "SHADOW_ESTIMATE"
    NO_UMSE_EDGE = "NO_UMSE_EDGE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    PROTOCOL_INELIGIBLE = "PROTOCOL_INELIGIBLE"


class MarketState(str, Enum):
    BALANCED_AUCTION = "BALANCED_AUCTION"
    INFORMED_ACCUMULATION = "INFORMED_ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"
    LIQUIDITY_VACUUM = "LIQUIDITY_VACUUM"
    SHORT_COVERING = "SHORT_COVERING"
    FORCED_LIQUIDATION = "FORCED_LIQUIDATION"
    DIRECTIONAL_CASCADE = "DIRECTIONAL_CASCADE"
    ABSORPTION = "ABSORPTION"
    TRANSITION = "TRANSITION"
    CHAOS_UNCERTAIN = "CHAOS_UNCERTAIN"


class Mechanism(str, Enum):
    INFORMED_BUYING = "INFORMED_BUYING"
    INFORMED_SELLING = "INFORMED_SELLING"
    SHORT_COVERING = "SHORT_COVERING"
    LONG_LIQUIDATION = "LONG_LIQUIDATION"
    PASSIVE_ACCUMULATION = "PASSIVE_ACCUMULATION"
    PASSIVE_DISTRIBUTION = "PASSIVE_DISTRIBUTION"
    LIQUIDITY_VACUUM = "LIQUIDITY_VACUUM"
    ABSORPTION = "ABSORPTION"
    BALANCED_NOISE = "BALANCED_NOISE"


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _finite01(value: float, name: str) -> float:
    x = float(value)
    if not math.isfinite(x) or x < 0.0 or x > 1.0:
        raise ValueError(f"{name} must be finite in [0,1]")
    return x


def _probabilities(values: Mapping[str, float], name: str) -> Dict[str, float]:
    if not values:
        raise ValueError(f"{name} must not be empty")
    out = {str(k): _finite01(v, f"{name}.{k}") for k, v in values.items()}
    total = sum(out.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"{name} must sum to 1.0; got {total}")
    return out


@dataclass(frozen=True)
class CausalObservation:
    event_time_utc: datetime
    available_time_utc: datetime
    ingested_time_utc: datetime
    source: str
    instrument: str
    data_class: DataClass
    quality_state: QualityState
    is_proxy: bool
    provenance_id: str
    value: Optional[float] = None

    def __post_init__(self) -> None:
        for field_name in ("source", "instrument", "provenance_id"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must be non-empty")
        object.__setattr__(self, "event_time_utc", _utc(self.event_time_utc))
        object.__setattr__(self, "available_time_utc", _utc(self.available_time_utc))
        object.__setattr__(self, "ingested_time_utc", _utc(self.ingested_time_utc))
        if self.value is not None and not math.isfinite(float(self.value)):
            raise ValueError("value must be finite when present")
        if self.data_class == DataClass.PROXY_RESEARCH and not self.is_proxy:
            raise ValueError("PROXY_RESEARCH must set is_proxy=True")
        if self.quality_state == QualityState.PROXY and not self.is_proxy:
            raise ValueError("PROXY quality must set is_proxy=True")

    def age_seconds(self, decision_time_utc: datetime) -> float:
        """Seconds between the event and the decision. Never negative."""
        return max(0.0, (_utc(decision_time_utc) - self.event_time_utc).total_seconds())

    def eligible_at(
        self, decision_time_utc: datetime, *, max_age_seconds: float | None = None
    ) -> bool:
        """Causal eligibility, optionally including a DERIVED staleness check.

        The audit found that nothing anywhere in the package derived staleness
        from timestamps: STALE was only ever a caller-supplied label, so a book
        or observation 30 days old was accepted in full provided somebody had
        labelled it FRESH. That put the entire staleness guarantee on whichever
        adapter set the label, with no defence in depth.

        `max_age_seconds` adds that second line of defence. It defaults to None
        -- meaning no age limit -- deliberately: a default value would be an
        invented constant, and the correct maximum age is instrument- and
        feed-specific. A real adapter MUST supply one. The label check below is
        retained, so this strengthens the contract and never weakens it.
        """
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
    def can_support_predictive_validation(self) -> bool:
        return self.data_class not in {
            DataClass.SYNTHETIC_TEST,
            DataClass.PROXY_RESEARCH,
        } and self.quality_state not in {
            QualityState.STALE,
            QualityState.MISSING,
            QualityState.INELIGIBLE,
            QualityState.PROXY,
        } and not self.is_proxy


@dataclass(frozen=True)
class LatentStateVector:
    directional_pressure: float
    liquidity_state: float
    aggression_urgency: float
    information_asymmetry: float
    resilience: float
    criticality: float
    structural_regime_entropy: float
    uncertainty: float

    def __post_init__(self) -> None:
        for field_name in (
            "directional_pressure",
            "liquidity_state",
            "aggression_urgency",
            "information_asymmetry",
            "resilience",
            "criticality",
            "structural_regime_entropy",
            "uncertainty",
        ):
            _finite01(getattr(self, field_name), field_name)


@dataclass(frozen=True)
class HorizonEstimate:
    horizon_hours: int
    state_probabilities: Mapping[str, float]
    mechanism_probabilities: Mapping[str, float]
    bullish_probability: float
    bearish_probability: float
    neutral_probability: float
    confidence: float
    propagation_probability: float
    data_quality_score: float
    reasons: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.horizon_hours not in (4, 8):
            raise ValueError("horizon_hours must be 4 or 8")
        object.__setattr__(
            self,
            "state_probabilities",
            _probabilities(self.state_probabilities, "state_probabilities"),
        )
        object.__setattr__(
            self,
            "mechanism_probabilities",
            _probabilities(self.mechanism_probabilities, "mechanism_probabilities"),
        )
        direction = {
            "bullish": _finite01(self.bullish_probability, "bullish_probability"),
            "bearish": _finite01(self.bearish_probability, "bearish_probability"),
            "neutral": _finite01(self.neutral_probability, "neutral_probability"),
        }
        total = sum(direction.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"directional probabilities must sum to 1.0; got {total}")
        _finite01(self.confidence, "confidence")
        _finite01(self.propagation_probability, "propagation_probability")
        _finite01(self.data_quality_score, "data_quality_score")


@dataclass(frozen=True)
class ShadowSnapshot:
    schema: str
    generated_at_utc: datetime
    decision_time_utc: datetime
    status: ShadowStatus
    latent_state: LatentStateVector
    estimates: Tuple[HorizonEstimate, HorizonEstimate]
    evidence_ids: Tuple[str, ...]
    data_classes_present: Tuple[str, ...]
    invalidation_reasons: Tuple[str, ...] = field(default_factory=tuple)
    production_effect: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "generated_at_utc", _utc(self.generated_at_utc))
        object.__setattr__(self, "decision_time_utc", _utc(self.decision_time_utc))
        if self.production_effect:
            raise ValueError("UMSE Phase 0/1 shadow snapshots cannot affect production")
        horizons = tuple(sorted(x.horizon_hours for x in self.estimates))
        if horizons != (4, 8):
            raise ValueError("exactly one 4H and one 8H estimate are required")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must be unique")

    def canonical_payload(self) -> dict:
        raw = asdict(self)
        raw["generated_at_utc"] = self.generated_at_utc.isoformat()
        raw["decision_time_utc"] = self.decision_time_utc.isoformat()
        raw["status"] = self.status.value
        return raw

    def provenance_hash(self) -> str:
        blob = json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()
