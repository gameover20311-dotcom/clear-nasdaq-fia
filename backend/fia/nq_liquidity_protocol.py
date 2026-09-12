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



"""CLEAR NASDAQ — nq_liquidity_truth split, PROTOCOL layer.

PROTOCOL — which instrument, which window, which source.

Quarterly contract eligibility, session windows, completed-session selection
and the Polygon/Yahoo fallback decision. _polygon_contract_rows and
_qqq_reference sit here rather than in INFRASTRUCTURE because they fetch a
SPECIFIC eligible instrument chosen by this layer, and they consume MODEL
parsers; keeping them below MODEL would have forced a circular import, which
is itself evidence of where the real seam is.

Bodies are moved VERBATIM. nq_liquidity_truth.py re-exports every name, so
`from .nq_liquidity_truth import ...` keeps working unchanged.
"""
from .nq_liquidity_infrastructure import _finite, _nq_tick, _qqq_tick, _raw_yahoo
from .nq_liquidity_model import (_normalize_polygon, _parse_yahoo,
                                 _daily_from_intraday, previous_completed_periods)


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

async def _select_polygon_contract(
    hub: Any,
) -> Dict[str, Any]:
    """
    SOL56_V2_EXPLICIT_CONTRACT_SELECTION

    1. Compare nearby quarterly NQ contracts using recent,
       point-in-time 5m volume.
    2. Freeze the dominant contract.
    3. Re-fetch enough history from that SAME contract for
       previous month/week/day and canonical session levels.
    """

    now_ny = datetime.now(
        timezone.utc
    ).astimezone(NY_TZ)

    candidates = _quarter_contracts(now_ny)

    tasks = [
        asyncio.create_task(
            _polygon_contract_rows(
                hub,
                contract,
                days=10,
            )
        )
        for contract in candidates
    ]

    results = await asyncio.gather(
        *tasks,
        return_exceptions=True,
    )

    scored = []

    for contract, result in zip(
        candidates,
        results,
    ):
        rows = (
            []
            if isinstance(result, Exception)
            else result
        )

        if not rows:
            continue

        recent_dates = sorted(
            {
                r["date"]
                for r in rows
                if r.get("date") is not None
            }
        )[-2:]

        recent = [
            r
            for r in rows
            if r.get("date") in recent_dates
        ]

        volume = sum(
            float(r.get("volume") or 0)
            for r in recent
        )

        scored.append(
            (
                volume,
                contract,
                rows,
            )
        )

    if not scored:
        return {
            "contract": None,
            "rows": [],
            "source": "MISSING",
            "candidate_volumes": {},
        }

    scored.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    selected_volume, contract, selection_rows = scored[0]

    # 75 days is comfortably below Massive's 50k bar limit
    # for 5-minute bars and preserves previous-month context.
    history_rows = await _polygon_contract_rows(
        hub,
        contract,
        days=75,
    )

    rows = history_rows or selection_rows

    return {
        "contract": contract,
        "rows": rows,
        "source": (
            "Massive Futures v1 explicit NQ contract "
            + contract
        ),
        "source_quality": "EXPLICIT_CONTRACT",
        "recent_volume": round(
            selected_volume,
            2,
        ),
        "candidate_volumes": {
            c: round(v, 2)
            for v, c, _ in scored
        },
        "history_days_requested": 75,
    }

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

