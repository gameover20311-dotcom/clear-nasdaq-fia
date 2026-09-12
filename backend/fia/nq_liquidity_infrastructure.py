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



"""CLEAR NASDAQ — nq_liquidity_truth split, INFRASTRUCTURE layer.

INFRASTRUCTURE — value coercion and raw transport.

Numeric coercion helpers and the raw Yahoo fetch. Nothing here decides what
counts as evidence or computes a level.

Bodies are moved VERBATIM. nq_liquidity_truth.py re-exports every name, so
`from .nq_liquidity_truth import ...` keeps working unchanged.
"""


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

