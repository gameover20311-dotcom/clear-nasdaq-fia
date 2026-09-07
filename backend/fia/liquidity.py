# CLEAR NASDAQ — FIA · LIQUIDITY GROUPS · ZERO-COST AUTONOMOUS NQ
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
    try:
        if current_price is None or level is None or float(current_price) == 0:
            return None
        return round(abs(float(level) - float(current_price)) / abs(float(current_price)) * 100, 3)
    except (TypeError, ValueError):
        return None


def _make_level(name, timeframe, side, instrument, price, current, source="", status=None):
    if price is None:
        clean_status = "MISSING"
    else:
        clean_status = status if status in {"TAPPED", "UNTAPPED"} else "UNKNOWN"
    return LiquidityLevel(
        name=name,
        timeframe=timeframe,
        price=price,
        status=clean_status,
        side=side,
        instrument=instrument,
        distance_pct=_distance_pct(current, price),
        detail=(f"{instrument} liquidity; same-instrument source={source}" if source else f"{instrument} liquidity"),
    )


def build_liquidity_groups(data: dict) -> Dict[str, Any]:
    qqq_meta = data.get("qqq_liquidity") or {}
    nq_meta = data.get("nq_liquidity") or {}

    qqq_current = qqq_meta.get("current_price", data.get("price"))
    nq_current = nq_meta.get("current_price", data.get("nq_futures_price"))

    period_specs = [
        ("monthly_high", "Previous Month High", "MONTHLY", "HIGH"),
        ("monthly_low", "Previous Month Low", "MONTHLY", "LOW"),
        ("weekly_high", "Previous Week High", "WEEKLY", "HIGH"),
        ("weekly_low", "Previous Week Low", "WEEKLY", "LOW"),
        ("daily_high", "Previous Day High", "DAILY", "HIGH"),
        ("daily_low", "Previous Day Low", "DAILY", "LOW"),
    ]
    session_specs = [
        ("asia_high", "Asia High", "ASIA", "HIGH"),
        ("asia_low", "Asia Low", "ASIA", "LOW"),
        ("london_high", "London High", "LONDON", "HIGH"),
        ("london_low", "London Low", "LONDON", "LOW"),
        ("new_york_high", "New York High", "NEW_YORK", "HIGH"),
        ("new_york_low", "New York Low", "NEW_YORK", "LOW"),
        ("london_close_high", "London Close High", "LONDON_CLOSE", "HIGH"),
        ("london_close_low", "London Close Low", "LONDON_CLOSE", "LOW"),
    ]

    nq_source = dict(nq_meta.get("levels") or {})
    qqq_source = dict(qqq_meta.get("levels") or {})
    nq_status = dict(nq_meta.get("level_status") or {})
    qqq_status = dict(qqq_meta.get("level_status") or {})
    nq_source_name = str(nq_meta.get("source") or "NQ source")
    qqq_source_name = str(qqq_meta.get("source") or "QQQ reference")

    nq_levels = {
        key: _make_level(name, tf, side, "NQ", nq_source.get(key), nq_current,
                         nq_source_name, nq_status.get(key))
        for key, name, tf, side in period_specs + session_specs
    }
    qqq_levels = {
        key: _make_level(name, tf, side, "QQQ", qqq_source.get(key), qqq_current,
                         qqq_source_name, qqq_status.get(key))
        for key, name, tf, side in period_specs
    }

    return {
        "nq": {
            "instrument": "NQ",
            "symbol": nq_meta.get("symbol"),
            "current_price": nq_current,
            "levels": nq_levels,
            "source": nq_source_name,
            "primary_chart_liquidity": True,
            "note": nq_meta.get("note"),
        },
        "qqq": {
            "instrument": "QQQ",
            "current_price": qqq_current,
            "levels": qqq_levels,
            "source": qqq_source_name,
            "primary_chart_liquidity": False,
        },
    }


def build_liquidity_map(data: dict) -> Dict[str, LiquidityLevel]:
    groups = build_liquidity_groups(data)
    flat: Dict[str, LiquidityLevel] = {}
    flat.update(groups["qqq"]["levels"])
    flat.update(groups["nq"]["levels"])
    return flat
