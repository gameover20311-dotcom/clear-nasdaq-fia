# PHASE22_TRUTH_CONSISTENCY_V1
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class LiquidityLevel:
    name: str
    timeframe: str
    price: Optional[float]
    status: str
    side: str
    instrument: str
    distance_pct: Optional[float] = None
    detail: str = ""


def _distance_pct(current_price: Optional[float], level: Optional[float]):
    if current_price is None or level is None or current_price == 0:
        return None
    return round(abs(level - current_price) / current_price * 100, 3)


def _make_level(name, timeframe, side, instrument, price, current):
    return LiquidityLevel(
        name=name,
        timeframe=timeframe,
        price=price,
        status="UNTAPPED" if price is not None else "MISSING",
        side=side,
        instrument=instrument,
        distance_pct=_distance_pct(current, price),
        detail=f"{instrument} liquidity; distance uses {instrument} current price",
    )


def build_liquidity_groups(data: dict) -> Dict[str, Any]:
    """Never compare QQQ prices with NQ futures levels (or vice versa)."""
    qqq_meta = data.get("qqq_liquidity") or {}
    nq_meta = data.get("nq_liquidity") or {}

    qqq_current = qqq_meta.get("current_price", data.get("price"))
    nq_current = nq_meta.get("current_price", data.get("nq_futures_price"))

    qqq_source = qqq_meta.get("levels") or data
    nq_source = nq_meta.get("levels") or data

    qqq_specs = [
        ("monthly_high", "Monthly High", "MONTHLY", "HIGH"),
        ("monthly_low", "Monthly Low", "MONTHLY", "LOW"),
        ("weekly_high", "Weekly High", "WEEKLY", "HIGH"),
        ("weekly_low", "Weekly Low", "WEEKLY", "LOW"),
        ("daily_high", "Daily High", "DAILY", "HIGH"),
        ("daily_low", "Daily Low", "DAILY", "LOW"),
    ]
    nq_specs = [
        ("asia_high", "Asia High", "ASIA", "HIGH"),
        ("asia_low", "Asia Low", "ASIA", "LOW"),
        ("london_high", "London High", "LONDON", "HIGH"),
        ("london_low", "London Low", "LONDON", "LOW"),
        ("new_york_high", "New York High", "NEW_YORK", "HIGH"),
        ("new_york_low", "New York Low", "NEW_YORK", "LOW"),
    ]

    qqq_levels = {
        key: _make_level(name, tf, side, "QQQ", qqq_source.get(key), qqq_current)
        for key, name, tf, side in qqq_specs
    }
    nq_levels = {
        key: _make_level(name, tf, side, "NQ", nq_source.get(key), nq_current)
        for key, name, tf, side in nq_specs
    }

    return {
        "qqq": {
            "instrument": "QQQ",
            "current_price": qqq_current,
            "levels": qqq_levels,
        },
        "nq": {
            "instrument": "NQ",
            "current_price": nq_current,
            "levels": nq_levels,
        },
    }


def build_liquidity_map(data: dict) -> Dict[str, LiquidityLevel]:
    """Backward-compatible flat map, with every level explicitly tagged."""
    groups = build_liquidity_groups(data)
    flat = {}
    flat.update(groups["qqq"]["levels"])
    flat.update(groups["nq"]["levels"])
    return flat
