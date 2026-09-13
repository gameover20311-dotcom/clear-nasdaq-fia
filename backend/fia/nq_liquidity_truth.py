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



"""CLEAR NASDAQ — nq_liquidity_truth facade over its three-way split.

WHY THIS MODULE WAS SPLIT
It mixed the same three identities providers.py did, proven by the code itself:
_period_level decides a published level (MODEL), _quarter_contracts decides which
instrument that level came from (PROTOCOL), and _raw_yahoo fetches it
(INFRASTRUCTURE). Those are different kinds of change sharing one file.

Nothing mathematical changed. Every body was moved verbatim, and the behaviour is
pinned by fia/test_nq_liquidity_truth_equivalence_v682.py against a baseline
recorded on the UNSPLIT module before this split existed.

The layering is INFRASTRUCTURE <- MODEL <- PROTOCOL, a strict DAG. An earlier
attempt placed the fetch helpers below MODEL and produced a circular import,
which was useful evidence: those helpers consume MODEL parsers and therefore
belong above it.

Every previously importable name is re-exported, so existing imports such as
`from .nq_liquidity_truth import apply_nq_chart_liquidity` are unaffected.
"""

from .nq_liquidity_infrastructure import (          # noqa: F401
    _finite, _nq_tick, _qqq_tick, _raw_yahoo,
)
from .nq_liquidity_model import (                    # noqa: F401
    _normalize_polygon, _parse_yahoo, _daily_from_intraday, _week_id,
    _period_level, _tapped_after_daily, previous_completed_periods,
)
from .nq_liquidity_protocol import (                 # noqa: F401
    _quarter_contracts, _window_for_date, latest_completed_sessions,
    _polygon_contract_rows, _select_polygon_contract, _free_nq_source,
    _qqq_reference,
)


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
