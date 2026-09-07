# CLEAR NASDAQ — FIA · ZERO-COST AUTONOMOUS NQ LIQUIDITY
# Primary: Polygon/Massive explicit NQ futures contract selected by recent volume.
# Fallback: Yahoo NQ=F. No TradingView webhook required.
# No broker execution. No forecast weights changed.
from __future__ import annotations

import asyncio
import calendar
import math
import time
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")
QQQ_SYMBOL = "QQQ"

# Match the user's TradingView session indicator settings.
SESSION_WINDOWS = {
    "asia": ((20, 0, -1), (0, 0, 0)),
    "london": ((2, 0, 0), (5, 0, 0)),
    "new_york": ((7, 0, 0), (12, 0, 0)),
    "london_close": ((10, 0, 0), (12, 0, 0)),
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


def _quarter_contracts(now_ny: datetime) -> List[str]:
    """Return nearby quarterly NQ contracts, e.g. on 2026-09-02 -> NQU6, NQZ6."""
    month_codes = [(3, "H"), (6, "M"), (9, "U"), (12, "Z")]
    year = now_ny.year

    # Current quarter is the first quarterly month >= current calendar month.
    current_idx = 0
    for i, (m, _) in enumerate(month_codes):
        if now_ny.month <= m:
            current_idx = i
            break
    else:
        current_idx = 0
        year += 1

    cur_m, cur_code = month_codes[current_idx]
    current = f"NQ{cur_code}{str(year)[-1]}"

    if current_idx < 3:
        _, next_code = month_codes[current_idx + 1]
        next_contract = f"NQ{next_code}{str(year)[-1]}"
    else:
        next_contract = f"NQH{str(year + 1)[-1]}"

    # Also include prior quarter because front-month often remains active
    # during the first days of a contract month.
    if current_idx > 0:
        _, prior_code = month_codes[current_idx - 1]
        prior_contract = f"NQ{prior_code}{str(year)[-1]}"
    else:
        prior_contract = f"NQZ{str(year - 1)[-1]}"

    return [prior_contract, current, next_contract]


def _normalize_polygon(candles: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not candles:
        return []
    ts = candles.get("t") or []
    highs = candles.get("h") or []
    lows = candles.get("l") or []
    closes = candles.get("c") or []
    volumes = candles.get("v") or []
    rows = []
    for i, raw_ts in enumerate(ts):
        try:
            dt = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc).astimezone(NY_TZ)
            h = _finite(highs[i] if i < len(highs) else None)
            l = _finite(lows[i] if i < len(lows) else None)
            c = _finite(closes[i] if i < len(closes) else None)
            v = _finite(volumes[i] if i < len(volumes) else 0) or 0.0
            if h is None or l is None:
                continue
            rows.append({
                "datetime": dt,
                "date": dt.date(),
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
            })
        except Exception:
            continue
    return rows


async def _polygon_contract_rows(hub: Any, contract: str, days: int = 45) -> List[Dict[str, Any]]:
    now_ny = datetime.now(timezone.utc).astimezone(NY_TZ)
    start = now_ny - timedelta(days=days)
    candles = await hub.polygon_futures_candles(
        contract,
        multiplier=5,
        timespan="minute",
        start_ts=int(start.timestamp()),
        end_ts=int(now_ny.timestamp()),
    )
    return _normalize_polygon(candles or {})


async def _select_polygon_contract(hub: Any) -> Dict[str, Any]:
    """Choose the actually active nearby NQ contract by recent 5m volume."""
    now_ny = datetime.now(timezone.utc).astimezone(NY_TZ)
    candidates = _quarter_contracts(now_ny)
    tasks = [asyncio.create_task(_polygon_contract_rows(hub, c, days=10)) for c in candidates]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scored = []
    for contract, result in zip(candidates, results):
        rows = [] if isinstance(result, Exception) else result
        # Last ~2 NY dates of volume to make rollover selection data-driven.
        recent_dates = sorted({r["date"] for r in rows})[-2:]
        recent = [r for r in rows if r["date"] in recent_dates]
        vol = sum(float(r.get("volume") or 0) for r in recent)
        if rows:
            scored.append((vol, contract, rows))

    if not scored:
        return {"contract": None, "rows": [], "source": "MISSING"}

    scored.sort(key=lambda x: x[0], reverse=True)
    vol, contract, rows = scored[0]
    return {
        "contract": contract,
        "rows": rows,
        "source": f"Polygon/Massive explicit NQ contract {contract}",
        "recent_volume": round(vol, 2),
        "candidate_volumes": {c: round(v, 2) for v, c, _ in scored},
    }


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
        payload = await hub.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
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
                rows.append({
                    "datetime": dt, "date": dt.date(),
                    "high": h, "low": l, "close": c, "volume": 0.0,
                })
            except Exception:
                continue
        current = next((_nq_tick(r["close"]) for r in reversed(rows) if r.get("close") is not None), None)
        if current is None:
            current = tick((result.get("meta") or {}).get("regularMarketPrice"))
        return {"rows": rows, "current_price": current}
    except Exception:
        return {"rows": [], "current_price": None}


def _daily_from_intraday(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[date, List[Dict[str, Any]]] = {}
    for r in rows:
        if r.get("date") is not None:
            grouped.setdefault(r["date"], []).append(r)
    out = []
    for d in sorted(grouped):
        subset = grouped[d]
        highs = [_finite(r.get("high")) for r in subset]
        lows = [_finite(r.get("low")) for r in subset]
        highs = [x for x in highs if x is not None]
        lows = [x for x in lows if x is not None]
        closes = [_finite(r.get("close")) for r in subset]
        closes = [x for x in closes if x is not None]
        if highs and lows:
            out.append({
                "date": d,
                "high": max(highs),
                "low": min(lows),
                "close": closes[-1] if closes else None,
            })
    return out


def _week_id(d: date):
    monday = d - timedelta(days=d.weekday())
    return monday


def _period_level(subset, side: str):
    vals = [_finite(r.get(side)) for r in subset]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return max(vals) if side == "high" else min(vals)


def _tapped_after_daily(daily_rows, cutoff_date: date, level: Optional[float], side: str) -> str:
    if level is None:
        return "MISSING"
    subsequent = [r for r in daily_rows if r.get("date") and r["date"] > cutoff_date]
    if side == "high":
        tapped = any((_finite(r.get("high")) or float("-inf")) >= level for r in subsequent)
    else:
        tapped = any((_finite(r.get("low")) or float("inf")) <= level for r in subsequent)
    return "TAPPED" if tapped else "UNTAPPED"


def previous_completed_periods(daily_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """PDH/PDL, PWH/PWL, PMH/PML — never current incomplete period."""
    if not daily_rows:
        return {"levels": {}, "status": {}, "origin": {}}
    rows = sorted([r for r in daily_rows if r.get("date")], key=lambda r: r["date"])
    anchor = rows[-1]["date"]

    # Previous completed trading day.
    prior_dates = sorted({r["date"] for r in rows if r["date"] < anchor})
    pd = prior_dates[-1] if prior_dates else None
    pd_rows = [r for r in rows if pd and r["date"] == pd]

    # Previous completed week.
    current_week = _week_id(anchor)
    prior_week_ids = sorted({_week_id(r["date"]) for r in rows if _week_id(r["date"]) < current_week})
    pw = prior_week_ids[-1] if prior_week_ids else None
    pw_rows = [r for r in rows if pw and _week_id(r["date"]) == pw]
    pw_end = max((r["date"] for r in pw_rows), default=None)

    # Previous completed calendar month that has data.
    current_month = (anchor.year, anchor.month)
    month_ids = sorted({(r["date"].year, r["date"].month) for r in rows
                        if (r["date"].year, r["date"].month) < current_month})
    pm = month_ids[-1] if month_ids else None
    pm_rows = [r for r in rows if pm and (r["date"].year, r["date"].month) == pm]
    pm_end = max((r["date"] for r in pm_rows), default=None)

    levels = {
        "daily_high": _nq_tick(_period_level(pd_rows, "high")),
        "daily_low": _nq_tick(_period_level(pd_rows, "low")),
        "weekly_high": _nq_tick(_period_level(pw_rows, "high")),
        "weekly_low": _nq_tick(_period_level(pw_rows, "low")),
        "monthly_high": _nq_tick(_period_level(pm_rows, "high")),
        "monthly_low": _nq_tick(_period_level(pm_rows, "low")),
    }
    status = {
        "daily_high": _tapped_after_daily(rows, pd, levels["daily_high"], "high") if pd else "MISSING",
        "daily_low": _tapped_after_daily(rows, pd, levels["daily_low"], "low") if pd else "MISSING",
        "weekly_high": _tapped_after_daily(rows, pw_end, levels["weekly_high"], "high") if pw_end else "MISSING",
        "weekly_low": _tapped_after_daily(rows, pw_end, levels["weekly_low"], "low") if pw_end else "MISSING",
        "monthly_high": _tapped_after_daily(rows, pm_end, levels["monthly_high"], "high") if pm_end else "MISSING",
        "monthly_low": _tapped_after_daily(rows, pm_end, levels["monthly_low"], "low") if pm_end else "MISSING",
    }
    origin = {
        "daily": pd.isoformat() if pd else None,
        "weekly": pw.isoformat() if pw else None,
        "monthly": f"{pm[0]:04d}-{pm[1]:02d}" if pm else None,
        "anchor_date": anchor.isoformat(),
    }
    return {"levels": levels, "status": status, "origin": origin}


def _window_for_date(name: str, target_date: date):
    (sh, sm, sday), (eh, em, eday) = SESSION_WINDOWS[name]
    sd = target_date + timedelta(days=sday)
    ed = target_date + timedelta(days=eday)
    start = datetime(sd.year, sd.month, sd.day, sh, sm, tzinfo=NY_TZ)
    end = datetime(ed.year, ed.month, ed.day, eh, em, tzinfo=NY_TZ)
    return start, end


def latest_completed_sessions(rows: List[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
    now_ny = (now or datetime.now(timezone.utc)).astimezone(NY_TZ)
    levels: Dict[str, Any] = {}
    status: Dict[str, str] = {}
    origins: Dict[str, Any] = {}

    for name in SESSION_WINDOWS:
        chosen = None
        for days_back in range(0, 8):
            target = now_ny.date() - timedelta(days=days_back)
            start, end = _window_for_date(name, target)
            if end > now_ny:
                continue  # completed sessions only
            subset = [r for r in rows if r.get("datetime") and start <= r["datetime"] < end]
            if subset:
                chosen = (target, start, end, subset)
                break
        if not chosen:
            levels[f"{name}_high"] = None
            levels[f"{name}_low"] = None
            status[f"{name}_high"] = "MISSING"
            status[f"{name}_low"] = "MISSING"
            continue

        target, start, end, subset = chosen
        hi = _nq_tick(max(_finite(r["high"]) for r in subset if _finite(r["high"]) is not None))
        lo = _nq_tick(min(_finite(r["low"]) for r in subset if _finite(r["low"]) is not None))
        levels[f"{name}_high"] = hi
        levels[f"{name}_low"] = lo
        later = [r for r in rows if r.get("datetime") and end <= r["datetime"] <= now_ny]
        status[f"{name}_high"] = "TAPPED" if any((_finite(r.get("high")) or float("-inf")) >= hi for r in later) else "UNTAPPED"
        status[f"{name}_low"] = "TAPPED" if any((_finite(r.get("low")) or float("inf")) <= lo for r in later) else "UNTAPPED"
        origins[name] = {
            "date": target.isoformat(),
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
    return {"levels": levels, "status": status, "origin": origins}


async def _free_nq_source(hub: Any) -> Dict[str, Any]:
    # Prefer user's already-configured Polygon/Massive futures infrastructure.
    try:
        poly = await _select_polygon_contract(hub)
        if poly.get("rows"):
            rows = poly["rows"]
            current = next((_nq_tick(r["close"]) for r in reversed(rows) if r.get("close") is not None), None)
            return {
                "rows": rows,
                "current_price": current,
                "symbol": poly["contract"],
                "source": poly["source"],
                "candidate_volumes": poly.get("candidate_volumes", {}),
                "quality": "EXPLICIT_CONTRACT",
            }
    except Exception:
        pass

    # Zero-cost public fallback.
    payload = await _raw_yahoo(hub, "NQ=F", "5m", 60)
    parsed = _parse_yahoo(payload, tick=_nq_tick)
    return {
        "rows": parsed["rows"],
        "current_price": parsed.get("current_price"),
        "symbol": "NQ=F",
        "source": "Yahoo NQ=F fallback",
        "candidate_volumes": {},
        "quality": "CONTINUOUS_FALLBACK",
    }


async def _qqq_reference(hub: Any) -> Dict[str, Any]:
    payload = await _raw_yahoo(hub, QQQ_SYMBOL, "1d", 75)
    parsed = _parse_yahoo(payload, tick=_qqq_tick)
    daily = _daily_from_intraday(parsed["rows"])
    # Reference only; use previous completed periods too.
    p = previous_completed_periods(daily)
    return {
        "current_price": parsed.get("current_price"),
        "levels": p["levels"],
        "status": p["status"],
        "origin": p["origin"],
    }


async def apply_nq_chart_liquidity(hub: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Autonomous, zero-cost liquidity. No TradingView webhook dependency."""
    nq_task = _free_nq_source(hub)
    qqq_task = _qqq_reference(hub)
    nq, qqq = await asyncio.gather(nq_task, qqq_task, return_exceptions=True)

    if isinstance(nq, Exception):
        nq = {"rows": [], "current_price": None, "symbol": None, "source": "MISSING", "quality": "MISSING"}
    if isinstance(qqq, Exception):
        qqq = {"current_price": None, "levels": {}, "status": {}, "origin": {}}

    intraday = nq.get("rows") or []
    daily = _daily_from_intraday(intraday)
    periods = previous_completed_periods(daily)
    sessions = latest_completed_sessions(intraday)

    levels = {}
    levels.update({k: v for k, v in periods["levels"].items() if v is not None})
    levels.update({k: v for k, v in sessions["levels"].items() if v is not None})
    statuses = {}
    statuses.update(periods["status"])
    statuses.update(sessions["status"])

    # Legacy dashboard fields become NQ liquidity fields, but main FIA forecast
    # price is NOT overwritten by this maintenance layer.
    for key, value in levels.items():
        data[key] = value

    data["nq_liquidity"] = {
        "instrument": "NQ",
        "symbol": nq.get("symbol"),
        "current_price": nq.get("current_price"),
        "levels": levels,
        "level_status": statuses,
        "source": nq.get("source"),
        "source_quality": nq.get("quality"),
        "timezone": "America/New_York",
        "period_origin": periods["origin"],
        "session_origin": sessions["origin"],
        "session_windows_ny": {
            "asia": "20:00 previous day -> 00:00",
            "london": "02:00 -> 05:00",
            "new_york": "07:00 -> 12:00",
            "london_close": "10:00 -> 12:00",
        },
        "tick_size": 0.25,
        "primary_chart_liquidity": True,
        "tradingview_webhook_required": False,
        "candidate_contract_volumes": nq.get("candidate_volumes", {}),
        "note": "NQ futures scale. It will not exactly equal FOREXCOM:NAS100 cash CFD.",
    }

    data["qqq_liquidity"] = {
        "instrument": "QQQ",
        "symbol": "QQQ",
        "current_price": qqq.get("current_price"),
        "levels": qqq.get("levels") or {},
        "level_status": qqq.get("status") or {},
        "origin": qqq.get("origin") or {},
        "source": "Yahoo QQQ reference",
        "primary_chart_liquidity": False,
    }

    data["liquidity_truth_fix"] = {
        "status": "ZERO_COST_AUTONOMOUS",
        "tradingview_webhook_required": False,
        "paid_dependency": False,
        "primary_instrument": "NQ futures",
        "exact_forexcom_cash_parity": False,
        "forecast_price_overwritten": False,
    }
    return data
