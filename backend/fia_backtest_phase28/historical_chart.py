# PHASE28_MARKET_GRADE_REPLAY_V1
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .phase28_data import FuturesCache, parse_dt

UTC = timezone.utc


def _floor_hours(dt: datetime, hours: int) -> datetime:
    dt = dt.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return dt.replace(hour=(dt.hour // hours) * hours)


def aggregate(rows: List[Dict[str, Any]], hours: int) -> List[Dict[str, Any]]:
    buckets: Dict[datetime, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        buckets[_floor_hours(r["timestamp"], hours)].append(r)
    out = []
    for start in sorted(buckets):
        rs = sorted(buckets[start], key=lambda x: x["timestamp"])
        if not rs:
            continue
        out.append({
            "timestamp": start,
            "open": rs[0]["open"],
            "high": max(x["high"] for x in rs),
            "low": min(x["low"] for x in rs),
            "close": rs[-1]["close"],
            "volume": sum(x.get("volume", 0.0) for x in rs),
        })
    return out


def atr(bars: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    if len(bars) < max(3, period + 1):
        return None
    vals = []
    for i in range(1, len(bars)):
        cur, prev = bars[i], bars[i-1]
        tr = max(
            cur["high"] - cur["low"],
            abs(cur["high"] - prev["close"]),
            abs(cur["low"] - prev["close"]),
        )
        vals.append(tr)
    vals = vals[-period:]
    return sum(vals) / len(vals) if vals else None


def ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2.0 / (period + 1.0)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1.0 - k)
    return e


def structure_direction(one_hour: List[Dict[str, Any]]) -> str:
    if len(one_hour) < 24:
        return "UNKNOWN"
    closes = [float(x["close"]) for x in one_hour]
    e20 = ema(closes[-60:], 20)
    if e20 is None:
        return "UNKNOWN"
    slope = closes[-1] - closes[-5]
    noise = max(1e-9, sum(abs(closes[i] - closes[i-1]) for i in range(len(closes)-8, len(closes))) / 7.0)
    if closes[-1] > e20 and slope > 0.35 * noise:
        return "BULLISH"
    if closes[-1] < e20 and slope < -0.35 * noise:
        return "BEARISH"
    return "NEUTRAL"


def _overlaps(lo: float, hi: float, price_lo: float, price_hi: float, pad: float = 0.0) -> bool:
    return not (price_hi < lo - pad or price_lo > hi + pad)


def detect_fvg(bars4h: List[Dict[str, Any]], recent5m: List[Dict[str, Any]]) -> Dict[str, Any]:
    a = atr(bars4h, 14)
    if not a or len(bars4h) < 6:
        return {"present": False}
    current = recent5m[-1]["close"] if recent5m else bars4h[-1]["close"]
    recent_lo = min((r["low"] for r in recent5m[-48:]), default=current)
    recent_hi = max((r["high"] for r in recent5m[-48:]), default=current)
    candidates = []
    # Exclude the latest 4H bucket if it may be partial; source 5m is PTI safe but
    # a forming HTF candle should not become a completed pattern anchor.
    for i in range(2, max(2, len(bars4h)-1)):
        b0, b2 = bars4h[i-2], bars4h[i]
        # bullish FVG: current low > candle two bars ago high
        if b2["low"] > b0["high"]:
            lo, hi = b0["high"], b2["low"]
            if hi - lo >= 0.10 * a:
                invalid = any(x["low"] <= lo for x in bars4h[i+1:])
                if not invalid:
                    candidates.append((i, "BULLISH", lo, hi))
        # bearish FVG
        if b2["high"] < b0["low"]:
            lo, hi = b2["high"], b0["low"]
            if hi - lo >= 0.10 * a:
                invalid = any(x["high"] >= hi for x in bars4h[i+1:])
                if not invalid:
                    candidates.append((i, "BEARISH", lo, hi))
    if not candidates:
        return {"present": False}
    i, side, lo, hi = candidates[-1]
    near = _overlaps(lo, hi, recent_lo, recent_hi, pad=0.20*a) or (lo - 0.20*a <= current <= hi + 0.20*a)
    if not near:
        return {"present": False}
    return {
        "present": True,
        "direction": side,
        "zone_low": round(lo, 4),
        "zone_high": round(hi, 4),
        "source": "deterministic_4h_ohlc",
    }


def detect_order_block(bars4h: List[Dict[str, Any]], recent5m: List[Dict[str, Any]]) -> Dict[str, Any]:
    a = atr(bars4h, 14)
    if not a or len(bars4h) < 8:
        return {"present": False}
    current = recent5m[-1]["close"] if recent5m else bars4h[-1]["close"]
    recent_lo = min((r["low"] for r in recent5m[-48:]), default=current)
    recent_hi = max((r["high"] for r in recent5m[-48:]), default=current)
    candidates = []
    for i in range(1, len(bars4h)-2):
        ob = bars4h[i]
        nxt = bars4h[i+1]
        rng = nxt["high"] - nxt["low"]
        if ob["close"] < ob["open"] and nxt["close"] > ob["high"] and rng >= 1.10*a:
            invalid = any(x["close"] < ob["low"] for x in bars4h[i+2:])
            if not invalid:
                candidates.append((i, "BULLISH", ob["low"], ob["high"]))
        if ob["close"] > ob["open"] and nxt["close"] < ob["low"] and rng >= 1.10*a:
            invalid = any(x["close"] > ob["high"] for x in bars4h[i+2:])
            if not invalid:
                candidates.append((i, "BEARISH", ob["low"], ob["high"]))
    if not candidates:
        return {"present": False}
    i, side, lo, hi = candidates[-1]
    near = _overlaps(lo, hi, recent_lo, recent_hi, pad=0.20*a) or (lo - 0.20*a <= current <= hi + 0.20*a)
    if not near:
        return {"present": False}
    return {
        "present": True,
        "direction": side,
        "zone_low": round(lo, 4),
        "zone_high": round(hi, 4),
        "source": "deterministic_4h_displacement",
    }


def _session_levels(rows: List[Dict[str, Any]], start: datetime, end: datetime) -> Optional[Tuple[float, float]]:
    rs = [r for r in rows if start <= r["timestamp"] < end]
    if not rs:
        return None
    return max(r["high"] for r in rs), min(r["low"] for r in rs)


def liquidity_sweep(rows: List[Dict[str, Any]], target: datetime) -> Dict[str, Any]:
    if len(rows) < 40:
        return {"present": False}
    target = target.astimezone(UTC)
    recent_start = target - timedelta(minutes=90)
    recent = [r for r in rows if r["timestamp"] >= recent_start]
    if not recent:
        return {"present": False}
    current = recent[-1]["close"]
    d = target.date()
    refs = []
    # Same-day Asia is complete well before the standard 17:00 UTC replay checkpoint.
    asia = _session_levels(rows, datetime(d.year,d.month,d.day,0,0,tzinfo=UTC), datetime(d.year,d.month,d.day,9,0,tzinfo=UTC))
    if asia:
        refs.append(("ASIA_HIGH", asia[0], "HIGH")); refs.append(("ASIA_LOW", asia[1], "LOW"))
    # Earlier London range only, excluding the recent 90m used to detect the sweep.
    london_end = min(recent_start, datetime(d.year,d.month,d.day,17,0,tzinfo=UTC))
    london = _session_levels(rows, datetime(d.year,d.month,d.day,8,0,tzinfo=UTC), london_end)
    if london:
        refs.append(("LONDON_PREFIX_HIGH", london[0], "HIGH")); refs.append(("LONDON_PREFIX_LOW", london[1], "LOW"))
    # Previous NY session.
    pd = d - timedelta(days=1)
    prevny = _session_levels(rows, datetime(pd.year,pd.month,pd.day,13,0,tzinfo=UTC), datetime(pd.year,pd.month,pd.day,22,0,tzinfo=UTC))
    if prevny:
        refs.append(("PREV_NY_HIGH", prevny[0], "HIGH")); refs.append(("PREV_NY_LOW", prevny[1], "LOW"))

    events = []
    for name, level, kind in refs:
        if kind == "LOW":
            swept = [r for r in recent if r["low"] < level]
            if swept and current > level:
                events.append({
                    "level": name, "price": level, "direction": "BULLISH",
                    "event": "SELL-SIDE LOW SWEEP RECLAIM",
                    "event_time": swept[-1]["timestamp"].isoformat(),
                    "_event_dt": swept[-1]["timestamp"],
                })
        elif kind == "HIGH":
            swept = [r for r in recent if r["high"] > level]
            if swept and current < level:
                events.append({
                    "level": name, "price": level, "direction": "BEARISH",
                    "event": "BUY-SIDE HIGH SWEEP REJECT",
                    "event_time": swept[-1]["timestamp"].isoformat(),
                    "_event_dt": swept[-1]["timestamp"],
                })
    if not events:
        return {"present": False}
    latest = max(event["_event_dt"] for event in events)
    latest_events = [event for event in events if event["_event_dt"] == latest]
    directions = {event["direction"] for event in latest_events}
    direction = next(iter(directions)) if len(directions) == 1 else "MIXED"
    public_events = [
        {key: value for key, value in event.items() if key != "_event_dt"}
        for event in latest_events[:4]
    ]
    return {
        "present": True,
        "direction": direction,
        "events": public_events,
        "source": "NQ_5m_completed_bars_independent_detection",
    }


def execution_confirmation(rows: List[Dict[str, Any]], target: datetime, liquidity: Dict[str, Any]) -> Dict[str, Any]:
    if not liquidity.get("present"):
        return {"present": False}
    recent = [r for r in rows if r["timestamp"] >= target - timedelta(minutes=75)]
    if len(recent) < 8:
        return {"present": False}
    last = recent[-1]
    prior = recent[-8:-1]
    direction = str(liquidity.get("direction") or "").upper()
    if direction == "BULLISH":
        confirmed = last["close"] > max(r["high"] for r in prior)
    elif direction == "BEARISH":
        confirmed = last["close"] < min(r["low"] for r in prior)
    else:
        return {"present": False}
    if not confirmed:
        return {"present": False}
    return {"present": True, "direction": direction, "event": "5m structure break after sweep", "source": "NQ_5m_completed_bars"}


def smt_divergence(nq_rows: List[Dict[str, Any]], es_rows: List[Dict[str, Any]], target: datetime) -> Dict[str, Any]:
    if len(nq_rows) < 60 or len(es_rows) < 60:
        return {"present": False, "reason": "ES/NQ 5m history unavailable"}
    ref_start = target - timedelta(hours=6)
    recent_start = target - timedelta(minutes=90)
    nq_ref = [r for r in nq_rows if ref_start <= r["timestamp"] < recent_start]
    es_ref = [r for r in es_rows if ref_start <= r["timestamp"] < recent_start]
    nq_recent = [r for r in nq_rows if r["timestamp"] >= recent_start]
    es_recent = [r for r in es_rows if r["timestamp"] >= recent_start]
    if min(len(nq_ref),len(es_ref),len(nq_recent),len(es_recent)) < 3:
        return {"present": False}
    nq_hi, nq_lo = max(r["high"] for r in nq_ref), min(r["low"] for r in nq_ref)
    es_hi, es_lo = max(r["high"] for r in es_ref), min(r["low"] for r in es_ref)
    nq_break_low = min(r["low"] for r in nq_recent) < nq_lo
    es_break_low = min(r["low"] for r in es_recent) < es_lo
    nq_break_high = max(r["high"] for r in nq_recent) > nq_hi
    es_break_high = max(r["high"] for r in es_recent) > es_hi
    bullish = nq_break_low != es_break_low
    bearish = nq_break_high != es_break_high
    if bullish and not bearish:
        return {"present": True, "direction": "BULLISH", "event": "NQ/ES sell-side SMT divergence", "source": "Massive NQ+ES 5m"}
    if bearish and not bullish:
        return {"present": True, "direction": "BEARISH", "event": "NQ/ES buy-side SMT divergence", "source": "Massive NQ+ES 5m"}
    if bullish and bearish:
        return {"present": True, "direction": "MIXED", "event": "Two-sided NQ/ES divergence", "source": "Massive NQ+ES 5m"}
    return {"present": False}


def build_historical_chart_analysis(
    target: datetime,
    fia_direction: str,
    nq: FuturesCache,
    es: Optional[FuturesCache] = None,
) -> Dict[str, Any]:
    target = parse_dt(target) or target
    nq_contract, nq_rows = nq.bars_asof(target, lookback_days=12)
    if not nq_rows:
        return {"direction": "UNKNOWN", "data_status": "NQ_MISSING", "nq_contract": nq_contract}
    h1 = aggregate(nq_rows, 1)
    h4 = aggregate(nq_rows, 4)
    chart_dir = structure_direction(h1)
    # Chart evidence is detected before and independently of the FIA forecast.
    # ``fia_direction`` remains in the signature only for API compatibility.
    fvg = detect_fvg(h4, nq_rows)
    ob = detect_order_block(h4, nq_rows)
    liq = liquidity_sweep(nq_rows, target)
    exe = execution_confirmation(nq_rows, target, liq)

    es_contract = None
    es_rows = []
    if es and es.available:
        es_contract, es_rows = es.bars_asof(target, lookback_days=2)
    smt = smt_divergence(nq_rows, es_rows, target) if es_rows else {"present": False, "reason": "ES cache missing"}

    in_ny = 13 <= target.hour < 22
    session = {
        "present": bool(in_ny and liq.get("present")),
        "direction": liq.get("direction") if in_ny and liq.get("present") else None,
        "session": "NEW_YORK" if in_ny else "OTHER",
        "source": "UTC session windows + completed NQ bars",
    }
    htf_present = bool(ob.get("present") or fvg.get("present"))
    htf_directions = {
        item.get("direction") for item in (ob, fvg)
        if item.get("present") and item.get("direction") in {"BULLISH", "BEARISH"}
    }
    htf_direction = next(iter(htf_directions)) if len(htf_directions) == 1 else "MIXED"
    htf = {
        "present": htf_present,
        "direction": htf_direction if htf_present else None,
        "source": "4H deterministic POI from OB/FVG",
    }

    def public(v: Dict[str, Any]) -> Any:
        if not v.get("present"):
            return None
        return {k: val for k, val in v.items() if k != "present"}

    return {
        "direction": chart_dir,
        "timeframe": "4H+1H+5M",
        "forecast_direction_used_for_detection": False,
        "htf_poi": public(htf),
        "htf_poi_direction": htf.get("direction") if htf_present else None,
        "order_block": public(ob),
        "order_block_direction": ob.get("direction") if ob.get("present") else None,
        "fvg": public(fvg),
        "fvg_direction": fvg.get("direction") if fvg.get("present") else None,
        "liquidity_sweep": public(liq),
        "liquidity_direction": liq.get("direction") if liq.get("present") else None,
        "smt": public(smt),
        "smt_direction": smt.get("direction") if smt.get("present") else None,
        "session_context": public(session),
        "session_direction": session.get("direction") if session.get("present") else None,
        "execution_confirmation": public(exe),
        "execution_direction": exe.get("direction") if exe.get("present") else None,
        "nq_contract": nq_contract,
        "es_contract": es_contract,
        "data_status": "REAL_NQ_ES" if es_rows else "REAL_NQ_ES_MISSING",
    }
