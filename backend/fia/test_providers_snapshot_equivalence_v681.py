#!/usr/bin/env python3
"""SNAPSHOT + NETWORK-BOUND EQUIVALENCE HARNESS (pre-split baseline, v681)

WHY A SECOND HARNESS
--------------------
v678 is PINNED at exactly 131 observations against
e2191da05e1a737c71ff88b3f5737b836d03974b6f784e9682a1595bd368e506. That value is
the approved unsplit baseline and must not be recalculated, so new coverage
cannot be added to it without destroying the comparison it exists to make. This
file carries its own pre-split baseline for the surface v678 does not reach.

WHAT IT COVERS
--------------
snapshot() — 797 lines, the largest and highest-risk method in providers.py, and
the one the split map records as itself three-way mixed. It computes
data['news'] (MODEL) while assembling provider health and eligibility (PROTOCOL)
and orchestrating fetches (INFRASTRUCTURE). It had no coverage at all.

Also the network-bound methods snapshot drives, plus the two enrichers it calls:
finnhub_quote, price_action_snapshot, get_nq_futures_live_price,
completed_bar_structure, fred_series, live_news_articles, get,
apply_nq_chart_liquidity and enrich_provider_reliability.

NO NETWORK, NO CLOCK
--------------------
Every provider method is replaced by a deterministic canned response and no
socket is opened. time is frozen inside the providers module, because snapshot()
builds the earnings-calendar window from time.strftime and would otherwise
produce a different result every day.

These are TEST FIXTURES. They are not historical data, not predictive data, and
they do not substitute for any missing archive. phase20 and phase28 stay
honestly MISSING_CANONICAL_DATA.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

try:
    from fia import providers as P
    from fia.providers import ProviderHub
except ModuleNotFoundError as _exc:        # pragma: no cover - environment gate
    print(f"NOT_TESTED_ENV: providers.py is not importable here ({_exc})")
    raise SystemExit(1)

# Recorded on UNSPLIT providers.py before the split. Never regenerated to make
# new code pass: a changed digest means changed behaviour.
# PINNED UNSPLIT BASELINE for snapshot() and the network-bound surface.
#
# PROVENANCE
#   value        45cdee64ce472a2abed1a48e1d5e2c11847907e51a3b3fdfb574eaaeff92ab57
#   observations 55
#   recorded on  UNSPLIT providers.py, before any split commit
#   hermetic     identical digest with normal egress AND with HTTPS_PROXY and
#                HTTP_PROXY pointed at a dead port, which proves no observation
#                depends on reaching a network.
#   frozen       time, datetime.now, yfinance.Ticker and httpx.AsyncClient are
#                all replaced, so neither the clock nor a provider can move it.
#
# Not recalculated after the split. A mismatch means the split changed
# behaviour: identify the first differing observation, never re-record.
BASELINE_DIGEST = "45cdee64ce472a2abed1a48e1d5e2c11847907e51a3b3fdfb574eaaeff92ab57"

FROZEN_EPOCH = 1780000000.0          # fixed instant; snapshot() reads the clock


class _FrozenTime:
    """Freeze exactly the time surface snapshot() uses."""

    def __init__(self, real):
        self._real = real

    def time(self):
        return FROZEN_EPOCH

    def strftime(self, fmt, t=None):
        return self._real.strftime(fmt, self._real.gmtime(
            FROZEN_EPOCH if t is None else (t if isinstance(t, float) else FROZEN_EPOCH)))

    def localtime(self, secs=None):
        return self._real.gmtime(FROZEN_EPOCH if secs is None else secs)

    def gmtime(self, secs=None):
        return self._real.gmtime(FROZEN_EPOCH if secs is None else secs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _FrozenDatetime(P.datetime):
    """datetime with a frozen now().

    snapshot()'s news block computes article ages from datetime.now(timezone.utc),
    so without this the age fields differ on every run and the digest is not
    reproducible. Everything else (fromisoformat, arithmetic, comparison) is
    inherited unchanged, so only the clock is frozen, not the semantics.
    """

    @classmethod
    def now(cls, tz=None):
        return P.datetime.fromtimestamp(FROZEN_EPOCH, tz or P.timezone.utc)


class _StubHTTPResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _StubAsyncClient:
    """Deterministic stand-in for httpx.AsyncClient.

    price_action_snapshot (providers.py) opens httpx directly rather than going
    through self.get, so stubbing self.get alone still let it reach the network.
    Verified by running under a dead proxy: it returned "403 Forbidden" until
    this stub existed, which is both a hermeticity break and a result that
    depends on whether the machine has egress.
    """

    def __init__(self, **_kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def get(self, url, params=None, headers=None, **_kw):
        return _StubHTTPResponse(_rest_for(str(url)))


class _StubTicker:
    """Deterministic stand-in for yfinance.Ticker. Opens no socket.

    Two methods reach yfinance directly rather than through self.get:
    get_session_liquidity (providers.py:4885) and get_nq_futures_live_price
    (providers.py:5615). Without this they attempt a real network call, which
    both breaks hermeticity and makes the observation depend on whether the
    machine happens to have egress.
    """

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, **_kw):
        import pandas as pd
        idx = pd.to_datetime(
            [1779990000, 1779993600, 1779997200], unit="s", utc=True
        ).tz_convert("America/New_York")
        return pd.DataFrame(
            {"Open": [19800.0, 19820.0, 19840.0],
             "High": [19900.0, 19910.0, 19920.0],
             "Low": [19750.0, 19760.0, 19770.0],
             "Close": [19850.0, 19860.0, 19870.0],
             "Volume": [1200, 1300, 1400]},
            index=idx,
        )


class _StubYF:
    Ticker = _StubTicker


def quote(c, d, dp, h, lo, o, pc, t=FROZEN_EPOCH):
    return {"c": c, "d": d, "dp": dp, "h": h, "l": lo, "o": o, "pc": pc, "t": t}


# One deterministic quote per symbol snapshot() asks for. Values are chosen to
# exercise the mega-cap, semiconductor and participation aggregations with a
# mixture of signs rather than a single direction.
QUOTES = {
    "QQQ":   quote(455.0, 3.2, 0.71, 456.1, 452.0, 453.0, 451.8),
    "SPY":   quote(560.0, 2.1, 0.38, 561.0, 558.0, 558.5, 557.9),
    "NVDA":  quote(131.0, 2.6, 2.02, 132.0, 128.5, 129.0, 128.4),
    "MSFT":  quote(430.0, -1.1, -0.26, 432.0, 429.0, 431.5, 431.1),
    "AAPL":  quote(224.0, 1.4, 0.63, 225.0, 222.5, 223.0, 222.6),
    "AMZN":  quote(186.0, -0.8, -0.43, 188.0, 185.5, 187.0, 186.8),
    "META":  quote(512.0, 4.0, 0.79, 514.0, 508.0, 509.0, 508.0),
    "AVGO":  quote(168.0, 3.1, 1.88, 169.0, 164.0, 165.0, 164.9),
    "GOOGL": quote(178.0, 0.5, 0.28, 179.0, 177.0, 177.5, 177.5),
    "GOOG":  quote(179.5, 0.6, 0.34, 180.0, 178.0, 179.0, 178.9),
    "TSLA":  quote(245.0, -3.2, -1.29, 250.0, 244.0, 248.0, 248.2),
    "AMD":   quote(142.0, 1.9, 1.36, 143.0, 140.0, 140.5, 140.1),
    "MU":    quote(102.0, -0.7, -0.68, 103.0, 101.5, 102.5, 102.7),
    "INTC":  quote(21.0, 0.2, 0.96, 21.2, 20.8, 20.9, 20.8),
    "QCOM":  quote(160.0, 1.1, 0.69, 161.0, 158.5, 159.0, 158.9),
    "SMCI":  quote(38.0, -1.5, -3.80, 40.0, 37.5, 39.5, 39.5),
}

CANDLES = {"c": [452.0, 453.5, 455.0], "h": [453.0, 454.0, 456.1],
           "l": [451.0, 452.5, 452.0], "o": [451.5, 452.0, 453.0],
           "t": [1779990000, 1779993600, 1779997200], "v": [1000, 1100, 1200],
           "s": "ok"}

ARTICLES = [
    {"title": "Nvidia beats on AI datacenter revenue, raises guidance",
     "description": "Chipmaker reports record quarter driven by accelerator demand.",
     "source": {"name": "Reuters"}, "publishedAt": "2026-05-29T15:30:00Z",
     "url": "https://r/1"},
    {"title": "Fed holds rates steady, signals patience on cuts",
     "description": "FOMC keeps target range unchanged.",
     "source": {"name": "Bloomberg"}, "publishedAt": "2026-05-29T14:00:00Z",
     "url": "https://b/2"},
    {"title": "Apple supplier warns on component shortage into H2",
     "description": "Guidance cut on constrained display supply.",
     "source": {"name": "WSJ"}, "publishedAt": "2026-05-29T09:00:00Z",
     "url": "https://w/4"},
]

EARNINGS = {"earningsCalendar": [
    {"symbol": "NVDA", "date": "2026-05-30", "epsEstimate": 1.2, "hour": "amc"},
    {"symbol": "AAPL", "date": "2026-06-01", "epsEstimate": 1.5, "hour": "bmo"},
]}

REST = {
    "quote": {"c": 455.0, "d": 3.2, "dp": 0.71, "h": 456.1, "l": 452.0,
              "o": 453.0, "pc": 451.8, "t": int(FROZEN_EPOCH)},
    "candles": dict(CANDLES),
    "company-news": [dict(a, datetime=int(FROZEN_EPOCH)) for a in ARTICLES],
    "news": [dict(a, datetime=int(FROZEN_EPOCH)) for a in ARTICLES],
    "observations": {"observations": [{"date": "2026-05-29", "value": "5.33"}]},
    "aggs": {"results": [{"t": 1779990000000, "o": 19800.0, "h": 19900.0,
                          "l": 19750.0, "c": 19850.0, "v": 1200}],
             "status": "OK", "resultsCount": 1},
    "newsapi": [dict(a) for a in ARTICLES],
    "price_action": {"trend": "up", "score": 0.35, "bars": 12,
                     "interval": "5m", "last_close": 455.0},
    "chart": {"chart": {"result": [{
        "meta": {"regularMarketPrice": 19850.25, "symbol": "NQ=F",
                 "exchangeTimezoneName": "America/New_York"},
        "timestamp": [1779990000, 1779993600, 1779997200],
        "indicators": {"quote": [{"open": [19800.0, 19820.0, 19840.0],
                                  "high": [19900.0, 19910.0, 19920.0],
                                  "low": [19750.0, 19760.0, 19770.0],
                                  "close": [19850.0, 19860.0, 19870.0],
                                  "volume": [1200, 1300, 1400]}]},
    }], "error": None}},
}

# Canned provider payloads, matched by URL. Ordering matters: newsapi.org
# returns an {"articles": [...]} envelope while Finnhub returns a bare list, and
# unified_news_feed fails on the wrong shape.
def _rest_for(url):
    u = str(url)
    if "calendar/earnings" in u:
        return EARNINGS
    if "series/observations" in u:
        return REST["observations"]
    if "newsapi.org" in u:
        return {"status": "ok", "totalResults": len(REST["newsapi"]),
                "articles": REST["newsapi"]}
    if "company-news" in u:
        return REST["company-news"]
    if "/news" in u:
        return REST["news"]
    if "quote" in u:
        return REST["quote"]
    if "candle" in u:
        return REST["candles"]
    if "aggs" in u:
        return REST["aggs"]
    if "chart" in u:
        return REST["chart"]
    if "priceaction" in u or "price-action" in u:
        return REST["price_action"]
    return None


obs: dict = {}


def rec(key, value):
    obs[key] = value


class Scenario:
    """A fully stubbed ProviderHub. Nothing here touches a socket."""

    def __init__(self, *, keys=None, quotes=QUOTES, candles=CANDLES,
                 articles=ARTICLES, fred=("5.33", "4.21"), nq_price=19850.25,
                 price_action=None, earnings=EARNINGS, enrichers_raise=False):
        self.keys = keys if keys is not None else {
            "FINNHUB_API_KEY": "TEST-FINNHUB", "FRED_API_KEY": "TEST-FRED",
            "POLYGON_API_KEY": "TEST-POLYGON", "NEWSAPI_KEY": "TEST-NEWSAPI",
        }
        self.quotes, self.candles, self.articles = quotes, candles, articles
        self.fred, self.nq_price, self.earnings = fred, nq_price, earnings
        self.enrichers_raise = enrichers_raise
        self.price_action = price_action if price_action is not None else {
            "trend": "up", "score": 0.35, "bars": 12, "interval": "5m",
            "source": "stub", "last_close": 455.0,
        }
        self.calls: list = []

    def build(self):
        hub = ProviderHub()
        hub.keys = dict(self.keys)
        s = self

        async def finnhub_quote(symbol):
            s.calls.append(("finnhub_quote", symbol))
            return s.quotes.get(symbol)

        async def price_action_snapshot(symbol, interval):
            s.calls.append(("price_action_snapshot", symbol, interval))
            return s.price_action

        async def get_nq_futures_live_price():
            s.calls.append(("get_nq_futures_live_price",))
            return s.nq_price

        async def completed_bar_structure(symbol, interval):
            s.calls.append(("completed_bar_structure", symbol, interval))
            if s.candles is None:
                return None
            # Shape matches the real return contract; snapshot() reads every
            # one of these keys directly and a missing one is a KeyError.
            return {
                "score": 0.42,
                "basis": f"{symbol}_{interval}M_CANDLES_COMPLETED_BARS",
                "completed_bars": 3,
                "last_completed_bar_start_utc": "2026-05-29T09:00:00+00:00",
                "last_completed_bar_end_utc": "2026-05-29T10:00:00+00:00",
                "source": "stub-candles",
                "detail": {"closes": 3, "interval": interval},
            }

        async def fred_series(series):
            s.calls.append(("fred_series", series))
            if s.fred is None:
                return None
            # Real shape: the FRED observations envelope, newest first.
            value = s.fred[0] if series == "DFF" else s.fred[1]
            return {"observations": [{"date": "2026-05-29", "value": value}],
                    "series_id": series}

        async def live_news_articles():
            s.calls.append(("live_news_articles",))
            if s.articles is None:
                return None
            return {"articles": list(s.articles), "provider": "stub-news",
                    "status": "ok"}

        async def get(url, params=None, timeout=10, headers=None):
            s.calls.append(("get", url))
            if "calendar/earnings" in url:
                return s.earnings
            return None

        hub.finnhub_quote = finnhub_quote
        hub.price_action_snapshot = price_action_snapshot
        hub.get_nq_futures_live_price = get_nq_futures_live_price
        hub.completed_bar_structure = completed_bar_structure
        hub.fred_series = fred_series
        hub.live_news_articles = live_news_articles
        hub.get = get
        return hub


def _install_enricher_stubs(raise_it):
    """Replace the two enrichers snapshot imports inside its own try blocks.

    They are imported by module path at call time, so patching the module
    attribute is what snapshot() will pick up. Real enrichment reaches the
    network; these stubs keep the run hermetic while still exercising both the
    success path and snapshot's documented DEGRADED fallback.
    """
    from fia import nq_liquidity_truth, provider_reliability

    async def liq(hub, data):
        if raise_it:
            raise RuntimeError("stubbed liquidity failure")
        data["nq_liquidity"] = {"source": "stub", "levels": {"pdh": 19900.0,
                                                             "pdl": 19750.0}}
        return data

    async def rel(hub, data):
        if raise_it:
            raise RuntimeError("stubbed reliability failure")
        data["provider_health"] = {"overall": "LIVE", "score": 0.94,
                                   "critical_missing": [], "stale_sources": [],
                                   "fallback_active": [], "available_sources":
                                   ["finnhub", "fred", "news"],
                                   "missing_sources": [], "rule": "stub"}
        data["provider_health_status"] = "LIVE"
        return data

    nq_liquidity_truth.apply_nq_chart_liquidity = liq
    provider_reliability.enrich_provider_reliability = rel


def run(label, scenario, raise_enrichers=False):
    real_time, real_dt, real_yf = P.time, P.datetime, P.yf
    P.time = _FrozenTime(real_time)
    P.datetime = _FrozenDatetime
    P.yf = _StubYF
    real_client = P.httpx.AsyncClient
    P.httpx.AsyncClient = _StubAsyncClient
    _install_enricher_stubs(raise_enrichers)
    try:
        hub = scenario.build()
        result = asyncio.run(hub.snapshot())
    except Exception as exc:
        rec(f"snapshot[{label}]", f"__RAISED__:{type(exc).__name__}:{exc}")
        return None
    finally:
        P.time, P.datetime, P.yf = real_time, real_dt, real_yf
        P.httpx.AsyncClient = real_client
    rec(f"snapshot[{label}]", result)
    rec(f"snapshot[{label}].calls", scenario.calls)
    return result


# ---- scenarios: every branch snapshot() can take ------------------------
run("happy_path", Scenario())
run("no_finnhub_key", Scenario(keys={"FINNHUB_API_KEY": "", "FRED_API_KEY": "F",
                                     "POLYGON_API_KEY": "P", "NEWSAPI_KEY": "N"}))
run("qqq_missing", Scenario(quotes={k: v for k, v in QUOTES.items() if k != "QQQ"}))
run("spy_missing", Scenario(quotes={k: v for k, v in QUOTES.items() if k != "SPY"}))
run("no_fred_key", Scenario(keys={"FINNHUB_API_KEY": "F", "FRED_API_KEY": "",
                                  "POLYGON_API_KEY": "P", "NEWSAPI_KEY": "N"}))
run("fred_unavailable", Scenario(fred=None))
run("fred_empty_observations", Scenario(fred=("", "")))
run("news_unavailable", Scenario(articles=None))
run("news_empty", Scenario(articles=[]))
run("no_structure", Scenario(candles=None))
run("no_price_action", Scenario(price_action=None))
run("no_nq_futures_price", Scenario(nq_price=None))
run("no_earnings", Scenario(earnings=None))
run("enrichment_fails", Scenario(), raise_enrichers=True)

# The cache is part of snapshot's contract: a second call inside the window must
# return the identical object without re-fetching.
_cache_scn = Scenario()
_first = run("cache_first", _cache_scn)
_real, _real_dt = P.time, P.datetime
P.time = _FrozenTime(_real)
P.datetime = _FrozenDatetime
_install_enricher_stubs(False)
try:
    _hub = _cache_scn.build()
    _a = asyncio.run(_hub.snapshot())
    _calls_after_first = len(_cache_scn.calls)
    _b = asyncio.run(_hub.snapshot())
    rec("snapshot[cache].second_call_identical", _a == _b)
    rec("snapshot[cache].no_extra_fetches",
        len(_cache_scn.calls) == _calls_after_first)
finally:
    P.time, P.datetime = _real, _real_dt


# ---- network-bound METHOD BODIES (TEST-FIXTURE-ONLY) --------------------
# The scenarios above stub these methods, which exercises snapshot() but NOT the
# methods' own logic. Here the real bodies run with only the transport (self.get)
# and the yfinance entry points replaced, so each method's branching, parsing and
# fallback selection is pinned without opening a socket.



def direct_hub():
    hub = ProviderHub()
    hub.keys = {"FRED_API_KEY": "TEST-FRED", "ALPHAVANTAGE_API_KEY": "TEST-AV",
                "FINNHUB_API_KEY": "TEST-FINNHUB", "POLYGON_API_KEY": "TEST-POLYGON",
                "NEWS_API_KEY": "TEST-NEWS", "PRICEACTION_API_KEY": "TEST-PA"}

    async def get(url, params=None, timeout=10, headers=None):
        return _rest_for(str(url))

    hub.get = get
    return hub


def direct(label, fn_name, *args, **kwargs):
    """Call a real method body with transport stubbed, and record the result."""
    real_time, real_dt, real_yf = P.time, P.datetime, P.yf
    P.time, P.datetime, P.yf = _FrozenTime(real_time), _FrozenDatetime, _StubYF
    _real_httpx_client = P.httpx.AsyncClient
    P.httpx.AsyncClient = _StubAsyncClient
    sys.modules['yfinance'] = _StubYF   # for the local re-import at :5612
    hub = direct_hub()
    try:
        fn = getattr(hub, fn_name)
        out = fn(*args, **kwargs)
        if asyncio.iscoroutine(out):
            out = asyncio.run(out)
        rec(f"direct[{label}]", out)
    except Exception as exc:
        rec(f"direct[{label}]", f"__RAISED__:{type(exc).__name__}:{exc}")
    finally:
        P.time, P.datetime, P.yf = real_time, real_dt, real_yf
        P.httpx.AsyncClient = _real_httpx_client
        sys.modules.pop('yfinance', None)


direct("finnhub_quote", "finnhub_quote", "QQQ")
_T0, _T1 = int(FROZEN_EPOCH) - 10800, int(FROZEN_EPOCH)
direct("finnhub_candles", "finnhub_candles", "QQQ", "60", _T0, _T1)
direct("finnhub_company_news", "finnhub_company_news", "AAPL")
direct("finnhub_market_news", "finnhub_market_news")
direct("fred_series[DFF]", "fred_series", "DFF")
direct("news_sentiment", "news_sentiment", "AAPL")
direct("now_ny", "now_ny")
direct("datetime_to_ts", "datetime_to_ts",
       P.datetime.fromtimestamp(FROZEN_EPOCH, P.timezone.utc))
direct("current_nq_futures_symbol", "current_nq_futures_symbol")
direct("price_action_snapshot", "price_action_snapshot", "QQQ", "5m")
direct("completed_bar_structure", "completed_bar_structure", "QQQ", "60")
direct("live_news_articles", "live_news_articles")
direct("unified_news_feed", "unified_news_feed")
direct("polygon_futures_candles", "polygon_futures_candles", "I:NDX", 5, "minute", _T0, _T1)
direct("_yahoo_chart_candles", "_yahoo_chart_candles", "NQ=F", "60", _T0, _T1)
direct("get_nq_futures_live_price", "get_nq_futures_live_price")
direct("liquidity", "liquidity", "QQQ")
direct("get_period_liquidity", "get_period_liquidity", "QQQ")
direct("get_session_liquidity", "get_session_liquidity", "NQ=F")
direct("get_nq_session_liquidity_yahoo", "get_nq_session_liquidity_yahoo")
direct("get_nq_liquidity_intelligence", "get_nq_liquidity_intelligence")

# __init__ moves in the split, so its observable outcome is pinned explicitly
# rather than left implicit in "a hub got constructed". Environment-derived key
# VALUES are deliberately not recorded; only the key set and the initial state.
def _init_shape():
    h = ProviderHub()
    return {
        "key_names": sorted(h.keys.keys()),
        "snapshot_cache": h._snapshot_cache,
        "snapshot_cache_time": h._snapshot_cache_time,
        "SNAPSHOT_CACHE_SECONDS": h.SNAPSHOT_CACHE_SECONDS,
        "price_action_cache_empty": h._price_action_cache == {},
        "price_action_cooldown_empty": h._price_action_cooldown_until == {},
        "attrs": sorted(k for k in vars(h) if not k.startswith("__")),
    }


rec("direct[__init__]", _init_shape())

# fred_series with no key must short-circuit before any transport call.
_nokey = direct_hub()
_nokey.keys["FRED_API_KEY"] = ""
rec("direct[fred_series:no_key]", asyncio.run(_nokey.fred_series("DFF")))


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
    print("BASELINE NOT YET PINNED. Record this digest into BASELINE_DIGEST, in "
          "the same commit, BEFORE the providers.py split.")
    raise SystemExit(1 if raised else 0)

if digest != BASELINE_DIGEST:
    print()
    print("=" * 60)
    print("SNAPSHOT EQUIVALENCE: FAIL — behaviour changed")
    print(f"expected {BASELINE_DIGEST}")
    print(f"got      {digest}")
    print("HARD STOP. Identify the first differing observation; do not re-record.")
    print("=" * 60)
    raise SystemExit(1)

print()
print("=" * 60)
print(f"SNAPSHOT EQUIVALENCE: PASS ({len(payload)} observations)")
print("snapshot() and its provider surface unchanged")
print("=" * 60)
