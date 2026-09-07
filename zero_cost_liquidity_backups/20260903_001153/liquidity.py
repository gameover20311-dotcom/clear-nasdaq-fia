# CLEAR NASDAQ — FIA · LIQUIDITY GROUPS · NQ CHART TRUTH
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


def _make_level(name, timeframe, side, instrument, price, current, source=""):
    return LiquidityLevel(
        name=name,
        timeframe=timeframe,
        price=price,
        status="UNTAPPED" if price is not None else "MISSING",
        side=side,
        instrument=instrument,
        distance_pct=_distance_pct(current, price),
        detail=(f"{instrument} liquidity; distance uses {instrument} current price" + (f"; source={source}" if source else "")),
    )


def _legacy_scale_levels(data: dict, current, keys):
    """Legacy fallback only when level and current price are plausibly same instrument.

    This prevents NQ ~29k levels from ever being presented as QQQ ~600 levels.
    """
    out = {}
    try:
        c = abs(float(current)) if current is not None else 0.0
    except (TypeError, ValueError):
        c = 0.0
    if c <= 0:
        return out
    for key in keys:
        value = data.get(key)
        try:
            v = abs(float(value))
        except (TypeError, ValueError):
            continue
        ratio = v / c if c else 0.0
        if 0.50 <= ratio <= 1.50:
            out[key] = value
    return out


def build_liquidity_groups(data: dict) -> Dict[str, Any]:
    """Primary chart liquidity is NQ. QQQ is an explicit reference only.

    Monthly/weekly/daily and Asia/London/New York levels are all allowed in the
    NQ group. Cross-instrument fallback is blocked by a price-scale sanity gate.
    """
    qqq_meta = data.get("qqq_liquidity") or {}
    nq_meta = data.get("nq_liquidity") or {}

    qqq_current = qqq_meta.get("current_price", data.get("price"))
    nq_current = nq_meta.get("current_price", data.get("nq_futures_price"))

    period_keys = ["monthly_high","monthly_low","weekly_high","weekly_low","daily_high","daily_low"]
    session_keys = ["asia_high","asia_low","london_high","london_low","new_york_high","new_york_low"]

    qqq_source = dict(qqq_meta.get("levels") or {})
    if not qqq_source:
        qqq_source = _legacy_scale_levels(data, qqq_current, period_keys)

    nq_source = dict(nq_meta.get("levels") or {})
    if not nq_source:
        nq_source = _legacy_scale_levels(data, nq_current, period_keys + session_keys)

    qqq_specs = [
        ("monthly_high", "Monthly High", "MONTHLY", "HIGH"),
        ("monthly_low", "Monthly Low", "MONTHLY", "LOW"),
        ("weekly_high", "Weekly High", "WEEKLY", "HIGH"),
        ("weekly_low", "Weekly Low", "WEEKLY", "LOW"),
        ("daily_high", "Daily High", "DAILY", "HIGH"),
        ("daily_low", "Daily Low", "DAILY", "LOW"),
    ]
    nq_specs = qqq_specs + [
        ("asia_high", "Asia High", "ASIA", "HIGH"),
        ("asia_low", "Asia Low", "ASIA", "LOW"),
        ("london_high", "London High", "LONDON", "HIGH"),
        ("london_low", "London Low", "LONDON", "LOW"),
        ("new_york_high", "New York High", "NEW_YORK", "HIGH"),
        ("new_york_low", "New York Low", "NEW_YORK", "LOW"),
    ]

    qqq_source_name = str(qqq_meta.get("source") or "QQQ reference")
    nq_source_name = str(nq_meta.get("source") or "NQ chart source")

    qqq_levels = {key: _make_level(name, tf, side, "QQQ", qqq_source.get(key), qqq_current, qqq_source_name)
                  for key, name, tf, side in qqq_specs}
    nq_levels = {key: _make_level(name, tf, side, "NQ", nq_source.get(key), nq_current, nq_source_name)
                 for key, name, tf, side in nq_specs}

    # NQ FIRST so the dashboard's first liquidity block is the chart instrument.
    return {
        "nq": {
            "instrument": "NQ",
            "current_price": nq_current,
            "levels": nq_levels,
            "source": nq_source_name,
            "primary_chart_liquidity": True,
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
    """Backward-compatible flat map. Duplicate period keys resolve to NQ."""
    groups = build_liquidity_groups(data)
    flat: Dict[str, LiquidityLevel] = {}
    # QQQ reference first; NQ overwrites duplicate monthly/weekly/daily keys.
    flat.update(groups["qqq"]["levels"])
    flat.update(groups["nq"]["levels"])
    return flat
