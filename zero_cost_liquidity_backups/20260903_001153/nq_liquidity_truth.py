# CLEAR NASDAQ — FIA · NQ LIQUIDITY TRUTH FIX
# Live chart-liquidity source: Yahoo NQ=F (continuous/front futures) + QQQ reference.
# No broker execution. No forecast weights changed.
from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")
NQ_SYMBOL = "NQ=F"
QQQ_SYMBOL = "QQQ"

# These are the project/chart session windows that existed before the later
# mixed-timezone regression. They are all explicitly America/New_York.
SESSION_WINDOWS = {
    "asia": ((20, 0, -1), (0, 0, 0)),
    "london": ((3, 0, 0), (8, 0, 0)),
    "new_york": ((9, 30, 0), (16, 0, 0)),
}

_CACHE: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}
_CACHE_LOCK = asyncio.Lock()


def _finite(value: Any) -> Optional[float]:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _nq_tick(value: Any) -> Optional[float]:
    x = _finite(value)
    if x is None:
        return None
    return round(round(x / 0.25) * 0.25, 2)


def _qqq_tick(value: Any) -> Optional[float]:
    x = _finite(value)
    return None if x is None else round(x, 2)


def _latest_trading_date(rows: List[Dict[str, Any]]):
    dates = [r.get("date") for r in rows if r.get("date") is not None]
    return max(dates) if dates else None


def _period_levels_from_rows(rows: List[Dict[str, Any]], tick=_nq_tick) -> Dict[str, Any]:
    """Build current daily/weekly/monthly candle extremes from DAILY bars.

    The latest available futures trading date anchors the day/week/month, so
    weekends/holidays cannot make the code silently fall back to the wrong
    calendar period.
    """
    if not rows:
        return {}
    anchor = _latest_trading_date(rows)
    if anchor is None:
        return {}

    daily = [r for r in rows if r.get("date") == anchor]
    week_start = anchor - timedelta(days=anchor.weekday())
    weekly = [r for r in rows if week_start <= r.get("date", anchor) <= anchor]
    monthly = [r for r in rows if r.get("date") and r["date"].year == anchor.year and r["date"].month == anchor.month]

    out: Dict[str, Any] = {"period_asof_date": anchor.isoformat()}
    for prefix, subset in (("daily", daily), ("weekly", weekly), ("monthly", monthly)):
        highs = [_finite(r.get("high")) for r in subset]
        lows = [_finite(r.get("low")) for r in subset]
        highs = [x for x in highs if x is not None]
        lows = [x for x in lows if x is not None]
        if highs:
            out[f"{prefix}_high"] = tick(max(highs))
        if lows:
            out[f"{prefix}_low"] = tick(min(lows))
    return out


def _window_for_date(name: str, target_date):
    start_spec, end_spec = SESSION_WINDOWS[name]
    sh, sm, sday = start_spec
    eh, em, eday = end_spec
    start_date = target_date + timedelta(days=sday)
    end_date = target_date + timedelta(days=eday)
    start = datetime(start_date.year, start_date.month, start_date.day, sh, sm, tzinfo=NY_TZ)
    end = datetime(end_date.year, end_date.month, end_date.day, eh, em, tzinfo=NY_TZ)
    return start, end


def _session_levels_from_rows(rows: List[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Use exact NY-time boundaries. No hour-only masks and no UTC/NY mixing."""
    if not rows:
        return {}
    now_ny = (now or datetime.now(timezone.utc)).astimezone(NY_TZ)
    out: Dict[str, Any] = {}
    session_dates: Dict[str, str] = {}

    # Each session independently chooses the most recent date with real bars.
    for name in ("asia", "london", "new_york"):
        for days_back in range(0, 8):
            target_date = now_ny.date() - timedelta(days=days_back)
            start, end = _window_for_date(name, target_date)
            effective_end = min(end, now_ny)
            if effective_end <= start:
                continue
            subset = [r for r in rows if r.get("datetime") and start <= r["datetime"] < effective_end]
            if not subset:
                continue
            highs = [_finite(r.get("high")) for r in subset]
            lows = [_finite(r.get("low")) for r in subset]
            highs = [x for x in highs if x is not None]
            lows = [x for x in lows if x is not None]
            if highs and lows:
                out[f"{name}_high"] = _nq_tick(max(highs))
                out[f"{name}_low"] = _nq_tick(min(lows))
                session_dates[name] = target_date.isoformat()
                break
    out["session_asof_dates"] = session_dates
    return out


async def _raw_yahoo(hub: Any, symbol: str, interval: str, days: int) -> Dict[str, Any]:
    ttl = 120.0 if interval == "1d" else 30.0
    key = (symbol, interval)
    cached = _CACHE.get(key)
    if cached and time.monotonic() - cached[0] < ttl:
        return cached[1]

    async with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and time.monotonic() - cached[0] < ttl:
            return cached[1]

        end_ts = int(datetime.now(timezone.utc).timestamp()) + 60
        start_ts = end_ts - days * 86400
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        payload = await hub.get(
            url,
            {
                "period1": start_ts,
                "period2": end_ts,
                "interval": interval,
                "events": "history",
                "includePrePost": "true",
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        if not isinstance(payload, dict):
            return {}
        _CACHE[key] = (time.monotonic(), payload)
        return payload


def _parse_yahoo(payload: Dict[str, Any], tick=_nq_tick) -> Dict[str, Any]:
    try:
        result = (payload.get("chart") or {}).get("result") or []
        if not result:
            return {"rows": [], "current_price": None}
        result = result[0]
        timestamps = result.get("timestamp") or []
        quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        rows = []
        for i, ts in enumerate(timestamps):
            try:
                dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(NY_TZ)
                h = _finite(highs[i] if i < len(highs) else None)
                l = _finite(lows[i] if i < len(lows) else None)
                c = _finite(closes[i] if i < len(closes) else None)
                if h is None or l is None:
                    continue
                rows.append({"datetime": dt, "date": dt.date(), "high": h, "low": l, "close": c})
            except Exception:
                continue
        current = None
        for r in reversed(rows):
            if r.get("close") is not None:
                current = tick(r["close"])
                break
        if current is None:
            meta_price = ((result.get("meta") or {}).get("regularMarketPrice"))
            current = tick(meta_price)
        return {"rows": rows, "current_price": current}
    except Exception:
        return {"rows": [], "current_price": None}


async def _symbol_daily(hub: Any, symbol: str, tick) -> Dict[str, Any]:
    payload = await _raw_yahoo(hub, symbol, "1d", 75)
    parsed = _parse_yahoo(payload, tick=tick)
    levels = _period_levels_from_rows(parsed["rows"], tick=tick)
    return {"levels": levels, "current_price": parsed.get("current_price")}


async def _nq_sessions(hub: Any) -> Dict[str, Any]:
    payload = await _raw_yahoo(hub, NQ_SYMBOL, "5m", 8)
    parsed = _parse_yahoo(payload, tick=_nq_tick)
    levels = _session_levels_from_rows(parsed["rows"])
    return {"levels": levels, "current_price": parsed.get("current_price")}


async def apply_nq_chart_liquidity(hub: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Mutate snapshot data so ALL chart liquidity levels are on the NQ price scale.

    QQQ remains an explicitly separate reference group. Legacy top-level
    liquidity keys are set to NQ levels to stop downstream code/UI from
    silently mixing a ~QQQ price with a ~NQ futures chart.
    """
    nq_daily_task = _symbol_daily(hub, NQ_SYMBOL, _nq_tick)
    nq_session_task = _nq_sessions(hub)
    qqq_daily_task = _symbol_daily(hub, QQQ_SYMBOL, _qqq_tick)
    nq_daily, nq_session, qqq_daily = await asyncio.gather(
        nq_daily_task, nq_session_task, qqq_daily_task, return_exceptions=True
    )

    if isinstance(nq_daily, Exception): nq_daily = {"levels": {}, "current_price": None}
    if isinstance(nq_session, Exception): nq_session = {"levels": {}, "current_price": None}
    if isinstance(qqq_daily, Exception): qqq_daily = {"levels": {}, "current_price": None}

    nq_levels: Dict[str, Any] = {}
    nq_levels.update({k: v for k, v in (nq_daily.get("levels") or {}).items() if k.endswith("_high") or k.endswith("_low")})
    nq_levels.update({k: v for k, v in (nq_session.get("levels") or {}).items() if k.endswith("_high") or k.endswith("_low")})
    qqq_levels = {k: v for k, v in (qqq_daily.get("levels") or {}).items() if k.endswith("_high") or k.endswith("_low")}

    nq_current = nq_session.get("current_price") or nq_daily.get("current_price") or _nq_tick(data.get("nq_futures_price"))
    qqq_current = qqq_daily.get("current_price") or _qqq_tick(data.get("price"))
    if nq_current is not None:
        data["nq_futures_price"] = nq_current

    # Legacy fields must now be NQ because the dashboard/chart liquidity panel
    # is an NQ panel. QQQ is retained only under qqq_liquidity.
    for key, value in nq_levels.items():
        data[key] = value

    data["nq_liquidity"] = {
        "instrument": "NQ",
        "symbol": NQ_SYMBOL,
        "current_price": nq_current,
        "levels": nq_levels,
        "source": "Yahoo NQ=F daily + 5m candles",
        "timezone": "America/New_York",
        "period_asof_date": (nq_daily.get("levels") or {}).get("period_asof_date"),
        "session_asof_dates": (nq_session.get("levels") or {}).get("session_asof_dates", {}),
        "session_windows_ny": {
            "asia": "20:00 previous day -> 00:00",
            "london": "03:00 -> 08:00",
            "new_york": "09:30 -> 16:00",
        },
        "tick_size": 0.25,
        "primary_chart_liquidity": True,
    }
    data["qqq_liquidity"] = {
        "instrument": "QQQ",
        "symbol": QQQ_SYMBOL,
        "current_price": qqq_current,
        "levels": qqq_levels,
        "source": "Yahoo QQQ daily candles",
        "primary_chart_liquidity": False,
    }
    data["liquidity_primary_instrument"] = "NQ"
    data["liquidity_evidence"] = {
        "nq": "available" if len(nq_levels) >= 6 else "partial" if nq_levels else "missing",
        "qqq_reference": "available" if qqq_levels else "missing",
    }
    # NQ alone is enough for the chart-liquidity truth panel. QQQ is reference only.
    data["liquidity_evidence_available"] = bool(nq_levels)
    data["liquidity_truth_fix"] = {
        "status": "ACTIVE",
        "bug_fixed": "QQQ period levels + NQ session levels were mixed in one NQ chart liquidity view",
        "period_levels": "NQ=F",
        "session_levels": "NQ=F",
        "qqq": "REFERENCE_ONLY",
    }
    return data
