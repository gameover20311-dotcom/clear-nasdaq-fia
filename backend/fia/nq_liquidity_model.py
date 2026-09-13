# CLEAR NASDAQ — FIA · ZERO-COST AUTONOMOUS NQ LIQUIDITY
# Primary: Massive Futures v1 explicit NQ contract selected by recent volume.
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



"""CLEAR NASDAQ — nq_liquidity_truth split, MODEL layer.

MODEL — feature computation for NQ liquidity levels.

Candle normalisation, daily aggregation, week bucketing, period level
selection and tap detection. A change here moves a published level, so it is
a change to the experiment. The arithmetic is untouched by the split.

Bodies are moved VERBATIM. nq_liquidity_truth.py re-exports every name, so
`from .nq_liquidity_truth import ...` keeps working unchanged.
"""
from .nq_liquidity_infrastructure import _finite, _nq_tick, _qqq_tick


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

