#!/usr/bin/env python3
"""NQ LIQUIDITY TRUTH EQUIVALENCE HARNESS (pre-split baseline, v682)

WHY
---
nq_liquidity_truth.py mixes identities the same way providers.py did, and the
evidence is in the module itself:

  feature computation (MODEL)      _normalize_polygon, _daily_from_intraday,
                                   _period_level, _tapped_after_daily,
                                   previous_completed_periods, _parse_yahoo
  instrument / session policy      _quarter_contracts (which quarterly contract
  (PROTOCOL)                       is eligible), _window_for_date and
                                   latest_completed_sessions (which session
                                   window counts), _select_polygon_contract and
                                   _free_nq_source (fallback selection)
  transport (INFRASTRUCTURE)       _polygon_contract_rows, _raw_yahoo,
                                   _qqq_reference

A change to _period_level moves a published level. A change to
_quarter_contracts changes WHICH instrument the level came from. Those are
different kinds of change and they were in one file.

This harness pins the behaviour BEFORE that file is split, exactly as v678 and
v681 do for providers.py. It opens no socket and reads no clock: every async
entry point runs against a stubbed hub and a frozen instant.

Mathematical behaviour is NOT changed by the split. This file is what proves it.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

try:
    from fia import nq_liquidity_truth as L
except ModuleNotFoundError as _exc:        # pragma: no cover - environment gate
    print(f"NOT_TESTED_ENV: nq_liquidity_truth is not importable here ({_exc})")
    raise SystemExit(1)

# PINNED UNSPLIT BASELINE for nq_liquidity_truth.py.
#   value        cfbc40bfeb3e00a25f68110caec0aeef3cf965978d7e057e33849f2e0fca3f24
#   observations 81, zero __RAISED__
#   recorded on  the UNSPLIT module, before any split commit
#   hermetic     identical with normal egress and with HTTPS_PROXY/HTTP_PROXY
#                pointed at a dead port
# Not recalculated after the split. A mismatch is a HARD STOP.
BASELINE_DIGEST = "cfbc40bfeb3e00a25f68110caec0aeef3cf965978d7e057e33849f2e0fca3f24"

FROZEN = datetime(2026, 5, 29, 20, 0, 0, tzinfo=timezone.utc)
NY = FROZEN.astimezone(L.ZoneInfo("America/New_York")) if hasattr(L, "ZoneInfo") else FROZEN

POLYGON = {"results": [
    {"t": 1779990000000, "o": 19800.0, "h": 19900.0, "l": 19750.0, "c": 19850.0, "v": 1200},
    {"t": 1779993600000, "o": 19850.0, "h": 19930.0, "l": 19780.0, "c": 19870.0, "v": 1300},
    {"t": 1780077000000, "o": 19870.0, "h": 19980.0, "l": 19820.0, "c": 19900.0, "v": 1400},
    {"t": 1780163400000, "o": 19900.0, "h": 20010.0, "l": 19850.0, "c": 19960.0, "v": 1500},
], "status": "OK", "resultsCount": 4}

YAHOO = {"chart": {"result": [{
    "meta": {"regularMarketPrice": 19960.0, "symbol": "NQ=F",
             "exchangeTimezoneName": "America/New_York"},
    "timestamp": [1779990000, 1779993600, 1780077000, 1780163400],
    "indicators": {"quote": [{
        "open": [19800.0, 19850.0, 19870.0, 19900.0],
        "high": [19900.0, 19930.0, 19980.0, 20010.0],
        "low": [19750.0, 19780.0, 19820.0, 19850.0],
        "close": [19850.0, 19870.0, 19900.0, 19960.0],
        "volume": [1200, 1300, 1400, 1500]}]},
}], "error": None}}

obs: dict = {}


def rec(key, value):
    obs[key] = value


def safe(key, fn, *a, **kw):
    try:
        rec(key, fn(*a, **kw))
    except Exception as exc:               # signature drift must stay visible
        rec(key, f"__RAISED__:{type(exc).__name__}:{exc}")


def asafe(key, coro_fn, *a, **kw):
    try:
        rec(key, asyncio.run(coro_fn(*a, **kw)))
    except Exception as exc:
        rec(key, f"__RAISED__:{type(exc).__name__}:{exc}")


class StubHub:
    """Deterministic hub. Every provider entry point returns canned data."""

    def __init__(self, polygon=POLYGON, yahoo=YAHOO, key="TEST-POLYGON"):
        self.keys = {"POLYGON_API_KEY": key}
        self._polygon, self._yahoo = polygon, yahoo

    async def polygon_futures_candles(self, ticker, multiplier=5, timespan="minute",
                                      start_ts=None, end_ts=None):
        # _polygon_contract_rows calls this on the hub, not hub.get.
        return self._polygon

    async def get(self, url, params=None, timeout=10, headers=None):
        u = str(url)
        if "aggs" in u or "polygon" in u:
            return self._polygon
        if "chart" in u or "yahoo" in u:
            return self._yahoo
        return None


# ---- value coercion (INFRASTRUCTURE) ------------------------------------
for v in (None, "", "abc", 0, 0.0, -1.5, 19850.25, float("inf"), float("nan"), "19850.25"):
    safe(f"_finite[{v!r}]", L._finite, v)
    safe(f"_nq_tick[{v!r}]", L._nq_tick, v)
    safe(f"_qqq_tick[{v!r}]", L._qqq_tick, v)

# ---- instrument eligibility (PROTOCOL) ----------------------------------
for month, day in ((1, 15), (3, 10), (3, 25), (6, 20), (9, 12), (12, 31)):
    probe = datetime(2026, month, day, 12, 0, tzinfo=timezone.utc)
    safe(f"_quarter_contracts[{month:02d}-{day:02d}]", L._quarter_contracts, probe)

# ---- parsing + feature computation (MODEL) ------------------------------
safe("_normalize_polygon", L._normalize_polygon, POLYGON)
safe("_normalize_polygon[empty]", L._normalize_polygon, {"results": []})
safe("_normalize_polygon[missing]", L._normalize_polygon, {})
safe("_parse_yahoo", L._parse_yahoo, YAHOO)
safe("_parse_yahoo[qqq_tick]", L._parse_yahoo, YAHOO, L._qqq_tick)
safe("_parse_yahoo[empty]", L._parse_yahoo, {"chart": {"result": []}})

ROWS = L._normalize_polygon(POLYGON)
rec("rows_fixture_len", len(ROWS))
safe("_daily_from_intraday", L._daily_from_intraday, ROWS)
safe("_daily_from_intraday[empty]", L._daily_from_intraday, [])

DAILY = L._daily_from_intraday(ROWS)
for d in (date(2026, 5, 27), date(2026, 5, 29), date(2026, 6, 1)):
    safe(f"_week_id[{d}]", L._week_id, d)
for side in ("high", "low"):
    safe(f"_period_level[{side}]", L._period_level, DAILY, side)
    safe(f"_period_level[{side}:empty]", L._period_level, [], side)
    for level in (None, 19900.0, 25000.0):
        safe(f"_tapped_after_daily[{side}:{level}]", L._tapped_after_daily,
             DAILY, date(2026, 5, 28), level, side)
safe("previous_completed_periods", L.previous_completed_periods, DAILY)
safe("previous_completed_periods[empty]", L.previous_completed_periods, [])

# ---- session windows (PROTOCOL) -----------------------------------------
for name in ("asia", "london", "new_york"):
    safe(f"_window_for_date[{name}]", L._window_for_date, name, date(2026, 5, 29))
try:
    L._window_for_date("unknown_session", date(2026, 5, 29))
    rec("_window_for_date[unknown:contract]", "DID_NOT_RAISE")
except KeyError:
    rec("_window_for_date[unknown:contract]", "KeyError")
safe("latest_completed_sessions", L.latest_completed_sessions, ROWS, FROZEN)
safe("latest_completed_sessions[empty]", L.latest_completed_sessions, [], FROZEN)

# ---- transport + fallback selection, hub stubbed ------------------------
asafe("_polygon_contract_rows", L._polygon_contract_rows, StubHub(), "NQM6")
asafe("_polygon_contract_rows[no_data]", L._polygon_contract_rows,
      StubHub(polygon={"results": []}), "NQM6")
asafe("_select_polygon_contract", L._select_polygon_contract, StubHub())
asafe("_select_polygon_contract[no_key]", L._select_polygon_contract, StubHub(key=""))
asafe("_raw_yahoo", L._raw_yahoo, StubHub(), "NQ=F", "60m", 5)
asafe("_free_nq_source", L._free_nq_source, StubHub())
asafe("_qqq_reference", L._qqq_reference, StubHub())

for label, hub in (("full", StubHub()),
                   ("no_polygon_key", StubHub(key="")),
                   ("empty_polygon", StubHub(polygon={"results": []})),
                   ("empty_yahoo", StubHub(yahoo={"chart": {"result": []}}))):
    data: dict = {}
    asafe(f"apply_nq_chart_liquidity[{label}]", L.apply_nq_chart_liquidity, hub, data)
    rec(f"apply_nq_chart_liquidity[{label}].data", data)


def _stable(value):
    if isinstance(value, (set, frozenset)):
        return sorted(_stable(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [_stable(v) for v in value]
    if isinstance(value, dict):
        return {k: _stable(v) for k, v in value.items()}
    return value


def canonical(value):
    return json.dumps(_stable(value), sort_keys=True, default=str,
                      separators=(",", ":"))


payload = {k: canonical(v) for k, v in sorted(obs.items())}
digest = hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()
raised = sorted(k for k, v in obs.items()
                if isinstance(v, str) and v.startswith("__RAISED__"))

print(f"observations : {len(payload)}")
print(f"digest       : {digest}")
if raised:
    print(f"RAISED       : {len(raised)}")
    for k in raised:
        print(f"   {k} -> {obs[k]}")

if BASELINE_DIGEST == "__RECORD_ON_UNSPLIT_CODE__":
    print()
    print("BASELINE NOT YET PINNED. Record this digest BEFORE splitting this module.")
    raise SystemExit(1 if raised else 0)

if digest != BASELINE_DIGEST:
    print()
    print("=" * 60)
    print("NQ LIQUIDITY TRUTH EQUIVALENCE: FAIL — behaviour changed")
    print(f"expected {BASELINE_DIGEST}")
    print(f"got      {digest}")
    print("HARD STOP. Identify the first differing observation; do not re-record.")
    print("=" * 60)
    raise SystemExit(1)

print()
print("=" * 60)
print(f"NQ LIQUIDITY TRUTH EQUIVALENCE: PASS ({len(payload)} observations)")
print("=" * 60)
