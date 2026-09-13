from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Iterable, Optional, Sequence, Tuple

from .contracts import DataClass, QualityState
from .events import EventType, MarketEvent


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _finite_nonnegative(x: float, name: str) -> float:
    y = float(x)
    if not math.isfinite(y) or y < 0:
        raise ValueError(f"{name} must be finite and >= 0")
    return y


@dataclass(frozen=True)
class BookLevel:
    price: float
    size: float
    order_count: Optional[int] = None

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.price)):
            raise ValueError("price must be finite")
        _finite_nonnegative(self.size, "size")
        if self.order_count is not None and int(self.order_count) < 0:
            raise ValueError("order_count must be >= 0")


@dataclass(frozen=True)
class OrderBookSnapshot:
    event_time_utc: datetime
    available_time_utc: datetime
    source: str
    instrument: str
    data_class: DataClass
    quality_state: QualityState
    provenance_id: str
    bids: Tuple[BookLevel, ...]
    asks: Tuple[BookLevel, ...]
    tick_size: float = 0.25
    is_proxy: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time_utc", _utc(self.event_time_utc))
        object.__setattr__(self, "available_time_utc", _utc(self.available_time_utc))
        if not str(self.source).strip() or not str(self.instrument).strip() or not str(self.provenance_id).strip():
            raise ValueError("source, instrument and provenance_id must be non-empty")
        if not self.bids or not self.asks:
            raise ValueError("book snapshot requires both bids and asks")
        if self.data_class not in {
            DataClass.REAL_LIVE_MBO,
            DataClass.REAL_HISTORICAL_MBO,
            DataClass.REAL_L2_DEPTH,
            DataClass.PROXY_RESEARCH,
            DataClass.SYNTHETIC_TEST,
        }:
            raise ValueError("book snapshot requires depth-capable data class")
        if self.data_class == DataClass.PROXY_RESEARCH and not self.is_proxy:
            raise ValueError("PROXY_RESEARCH must set is_proxy=True")
        if self.tick_size <= 0 or not math.isfinite(float(self.tick_size)):
            raise ValueError("tick_size must be finite and > 0")
        bids = tuple(sorted(self.bids, key=lambda x: x.price, reverse=True))
        asks = tuple(sorted(self.asks, key=lambda x: x.price))
        if bids[0].price >= asks[0].price:
            raise ValueError("crossed/locked book is not accepted by this research contract")
        object.__setattr__(self, "bids", bids)
        object.__setattr__(self, "asks", asks)

    @property
    def best_bid(self) -> float:
        return float(self.bids[0].price)

    @property
    def best_ask(self) -> float:
        return float(self.asks[0].price)

    @property
    def mid(self) -> float:
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread_ticks(self) -> float:
        return (self.best_ask - self.best_bid) / self.tick_size

    def age_seconds(self, decision_time_utc: datetime) -> float:
        return max(0.0, (_utc(decision_time_utc) - self.event_time_utc).total_seconds())

    def eligible_at(
        self, decision_time_utc: datetime, *, max_age_seconds: float | None = None
    ) -> bool:
        """See CausalObservation.eligible_at for why max_age_seconds has no default."""
        decision = _utc(decision_time_utc)
        if max_age_seconds is not None and self.age_seconds(decision) > float(max_age_seconds):
            return False
        return (
            self.available_time_utc <= decision
            and self.event_time_utc <= decision
            and self.quality_state not in {QualityState.STALE, QualityState.MISSING, QualityState.INELIGIBLE}
        )

    @property
    def exact_queue_identity_capable(self) -> bool:
        return self.data_class in {DataClass.REAL_LIVE_MBO, DataClass.REAL_HISTORICAL_MBO}


@dataclass(frozen=True)
class LiquidityField:
    mid: float
    spread_ticks: float
    bid_depth: float
    ask_depth: float
    weighted_bid_depth: float
    weighted_ask_depth: float
    depth_imbalance: float
    bid_gradient: float
    ask_gradient: float
    bid_curvature: float
    ask_curvature: float
    thinness: float
    cancellation_pressure: float
    replenishment_pressure: float
    resilience_proxy: float
    liquidity_credibility: float
    exact_queue_metrics_identifiable: bool
    calibrated: bool = False


def _weighted_depth(levels: Sequence[BookLevel], best: float, tick: float, decay: float) -> float:
    total = 0.0
    for level in levels:
        distance = abs(level.price - best) / tick
        total += float(level.size) * math.exp(-decay * distance)
    return total


def _polyfit(ys: Sequence[float], degree: int) -> list:
    """Least-squares polynomial coefficients [a0, a1, ...] for x = 0..n-1.

    Solved via the normal equations with Gaussian elimination. The book depth
    profiles here are at most a few dozen levels, so conditioning is not a
    practical concern at degree 1 or 2.
    """
    n = len(ys)
    m = degree + 1
    xs = list(range(n))
    # Normal equations: (X^T X) c = X^T y
    ata = [[sum(x ** (i + j) for x in xs) for j in range(m)] for i in range(m)]
    aty = [sum((x ** i) * ys[k] for k, x in enumerate(xs)) for i in range(m)]
    for col in range(m):
        pivot = max(range(col, m), key=lambda r: abs(ata[r][col]))
        if abs(ata[pivot][col]) < 1e-12:
            return [0.0] * m
        ata[col], ata[pivot] = ata[pivot], ata[col]
        aty[col], aty[pivot] = aty[pivot], aty[col]
        inv = 1.0 / ata[col][col]
        for r in range(m):
            if r == col:
                continue
            factor = ata[r][col] * inv
            if factor == 0.0:
                continue
            for c in range(col, m):
                ata[r][c] -= factor * ata[col][c]
            aty[r] -= factor * aty[col]
    return [aty[i] / ata[i][i] for i in range(m)]


def _normalized_gradient(levels: Sequence[BookLevel]) -> float:
    """Mean slope of the depth profile, by ordinary least squares.

    The previous implementation used (last - first) / (n - 1), which is the
    mean first difference. That telescopes: it reads only the two endpoint
    levels and discards the entire book interior, while still moving between
    books through the normalising mean -- responding to levels it does not
    measure. An OLS slope uses every level.
    """
    if len(levels) < 2:
        return 0.0
    sizes = [float(x.size) for x in levels]
    scale = max(1e-12, sum(sizes) / len(sizes))
    slope = _polyfit(sizes, 1)[1]
    return slope / scale


def _normalized_curvature(levels: Sequence[BookLevel]) -> float:
    """Second-order shape of the depth profile, by ordinary least squares.

    The previous implementation summed second differences, which telescopes to
    (s[-1] - s[-2]) - (s[1] - s[0]). The audit showed a linear ramp, a 900-lot
    interior wall and a complete interior hole all returning exactly 0.0.

    Fitting s = a + b*x + c*x^2 and reporting 2c gives a curvature that
    responds to every level. Sign convention: positive is convex (an interior
    dip, liquidity hollowed out in the middle), negative is concave (an
    interior wall).
    """
    if len(levels) < 3:
        return 0.0
    sizes = [float(x.size) for x in levels]
    scale = max(1e-12, sum(sizes) / len(sizes))
    quadratic = _polyfit(sizes, 2)[2]
    return (2.0 * quadratic) / scale


def _event_pressure(events: Iterable[MarketEvent], decision_time_utc: datetime) -> tuple[float, float, float]:
    decision = _utc(decision_time_utc)
    cancels = 0.0
    replen = 0.0
    mbo_identified = 0
    eligible = 0
    for e in events:
        if not e.eligible_at(decision) or e.event_time_utc > decision:
            continue
        eligible += 1
        size = float(e.size or 0.0)
        if e.event_type in {EventType.CANCEL_BID, EventType.CANCEL_ASK}:
            cancels += size
        elif e.event_type in {EventType.REPLENISH_BID, EventType.REPLENISH_ASK}:
            replen += size
        if e.has_true_order_identity:
            mbo_identified += 1
    total = cancels + replen
    cancellation_pressure = cancels / total if total > 0 else 0.0
    replenishment_pressure = replen / total if total > 0 else 0.0
    identity_fraction = mbo_identified / eligible if eligible else 0.0
    return cancellation_pressure, replenishment_pressure, identity_fraction


def estimate_liquidity_field(
    snapshot: OrderBookSnapshot,
    decision_time_utc: datetime,
    events: Iterable[MarketEvent] = (),
    *,
    levels: int = 10,
    distance_decay: float = 0.35,
    max_age_seconds: float | None = None,
) -> LiquidityField:
    if not snapshot.eligible_at(decision_time_utc, max_age_seconds=max_age_seconds):
        raise ValueError("snapshot is not causally eligible at decision time")
    if levels <= 0:
        raise ValueError("levels must be > 0")
    bids = snapshot.bids[:levels]
    asks = snapshot.asks[:levels]
    bid_depth = sum(float(x.size) for x in bids)
    ask_depth = sum(float(x.size) for x in asks)
    gross = bid_depth + ask_depth
    imbalance = (bid_depth - ask_depth) / gross if gross > 0 else 0.0
    weighted_bid = _weighted_depth(bids, snapshot.best_bid, snapshot.tick_size, distance_decay)
    weighted_ask = _weighted_depth(asks, snapshot.best_ask, snapshot.tick_size, distance_decay)
    weighted_total = weighted_bid + weighted_ask
    # Thinness is relative and bounded; it is not an exchange-independent absolute liquidity score.
    thinness = 1.0 / (1.0 + math.log1p(weighted_total))
    cancel_p, replen_p, identity_fraction = _event_pressure(events, decision_time_utc)
    resilience_proxy = replen_p * (1.0 - min(1.0, snapshot.spread_ticks / 8.0))
    # Credibility is a descriptive data-quality/liquidity-persistence proxy. Exact queue credibility
    # is only identifiable under true MBO with complete order identity.
    credibility = 0.5 * replen_p + 0.5 * identity_fraction
    exact = snapshot.exact_queue_identity_capable and identity_fraction == 1.0
    return LiquidityField(
        mid=snapshot.mid,
        spread_ticks=snapshot.spread_ticks,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        weighted_bid_depth=weighted_bid,
        weighted_ask_depth=weighted_ask,
        depth_imbalance=max(-1.0, min(1.0, imbalance)),
        bid_gradient=_normalized_gradient(bids),
        ask_gradient=_normalized_gradient(asks),
        bid_curvature=_normalized_curvature(bids),
        ask_curvature=_normalized_curvature(asks),
        thinness=max(0.0, min(1.0, thinness)),
        cancellation_pressure=max(0.0, min(1.0, cancel_p)),
        replenishment_pressure=max(0.0, min(1.0, replen_p)),
        resilience_proxy=max(0.0, min(1.0, resilience_proxy)),
        liquidity_credibility=max(0.0, min(1.0, credibility)),
        exact_queue_metrics_identifiable=exact,
        calibrated=False,
    )
