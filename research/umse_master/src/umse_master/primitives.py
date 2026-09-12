from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .events import EventType, EventWindow


@dataclass(frozen=True)
class PrimitiveFeatures:
    event_count: int
    buy_aggressive_volume: float
    sell_aggressive_volume: float
    signed_aggressive_volume: float
    aggression_imbalance: float
    cancellation_volume: float
    replenishment_volume: float
    replenishment_ratio: float
    buy_sweeps: int
    sell_sweeps: int
    large_buy_volume: float
    large_sell_volume: float
    first_price: Optional[float]
    last_price: Optional[float]
    observed_price_change: Optional[float]
    true_mbo_order_identity_fraction: float
    queue_survival_identifiable: bool


def _size(event) -> float:
    return float(event.size or 0.0)


def compute_primitives(
    window: EventWindow,
    decision_time_utc: datetime,
    start_time_utc: Optional[datetime] = None,
) -> PrimitiveFeatures:
    rows = window.causal_slice(decision_time_utc, start_time_utc)

    buy_aggr = sum(_size(e) for e in rows if e.event_type == EventType.BUY_AGGRESSION)
    sell_aggr = sum(_size(e) for e in rows if e.event_type == EventType.SELL_AGGRESSION)

    cancels = sum(
        _size(e)
        for e in rows
        if e.event_type in {EventType.CANCEL_BID, EventType.CANCEL_ASK}
    )
    replenishment = sum(
        _size(e)
        for e in rows
        if e.event_type in {EventType.REPLENISH_BID, EventType.REPLENISH_ASK}
    )

    buy_sweeps = sum(1 for e in rows if e.event_type == EventType.SWEEP_BUY)
    sell_sweeps = sum(1 for e in rows if e.event_type == EventType.SWEEP_SELL)

    large_buy = sum(_size(e) for e in rows if e.event_type == EventType.LARGE_TRADE_BUY)
    large_sell = sum(_size(e) for e in rows if e.event_type == EventType.LARGE_TRADE_SELL)

    gross_aggr = buy_aggr + sell_aggr
    imbalance = (buy_aggr - sell_aggr) / gross_aggr if gross_aggr > 0 else 0.0

    liquidity_turnover = replenishment + cancels
    replenishment_ratio = replenishment / liquidity_turnover if liquidity_turnover > 0 else 0.0

    priced = [e for e in rows if e.price is not None]
    first_price = float(priced[0].price) if priced else None
    last_price = float(priced[-1].price) if priced else None
    observed_change = (
        last_price - first_price
        if first_price is not None and last_price is not None
        else None
    )

    mbo_identified = sum(1 for e in rows if e.has_true_order_identity)
    identity_fraction = mbo_identified / len(rows) if rows else 0.0

    # Exact queue survival requires true individual-order identity. Aggregate L2
    # must never be upgraded into MBO semantics.
    queue_survival_identifiable = bool(rows) and identity_fraction == 1.0

    return PrimitiveFeatures(
        event_count=len(rows),
        buy_aggressive_volume=buy_aggr,
        sell_aggressive_volume=sell_aggr,
        signed_aggressive_volume=buy_aggr - sell_aggr,
        aggression_imbalance=imbalance,
        cancellation_volume=cancels,
        replenishment_volume=replenishment,
        replenishment_ratio=replenishment_ratio,
        buy_sweeps=buy_sweeps,
        sell_sweeps=sell_sweeps,
        large_buy_volume=large_buy,
        large_sell_volume=large_sell,
        first_price=first_price,
        last_price=last_price,
        observed_price_change=observed_change,
        true_mbo_order_identity_fraction=identity_fraction,
        queue_survival_identifiable=queue_survival_identifiable,
    )
