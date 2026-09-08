"""Regression for live candle fallback freshness and provider-log credential redaction."""
from __future__ import annotations

import asyncio
import io
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import httpx
from fia.providers import ProviderHub

FAIL = []


def check(name, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + name + ((" " + str(detail)) if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


print("[A] provider HTTP errors never print query-string secrets")
secret = "TOP_SECRET_FINNHUB_TOKEN_123"
req = httpx.Request("GET", "https://finnhub.io/api/v1/stock/candle?symbol=QQQ&token=" + secret)
resp = httpx.Response(403, request=req)


class FakeClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return resp


buf = io.StringIO()
with patch("fia.providers.httpx.AsyncClient", FakeClient), redirect_stdout(buf):
    got = asyncio.run(ProviderHub().get("https://finnhub.io/api/v1/stock/candle", {"token": secret}))
out = buf.getvalue()
check("request failed closed", got is None)
check("secret absent from log", secret not in out, out)
check("query key absent from log", "token=" not in out.lower(), out)
check("status retained for diagnosis", "HTTP 403" in out, out)

print("[B] fresher Yahoo series beats stale-but-valid Polygon series")
now = int(time.time())


class DeterministicHub(ProviderHub):
    def __init__(self):
        super().__init__()
        self.keys["FINNHUB_API_KEY"] = "x"
        self.keys["POLYGON_API_KEY"] = "y"

    async def get(self, url, params=None, timeout=10, headers=None):
        if "finnhub.io" in url:
            return None
        if "polygon.io" in url:
            rows = []
            for i in range(12):
                ts = (now - (15 - i) * 3600) * 1000
                rows.append({"t": ts, "o": 100 + i, "h": 102 + i, "l": 99 + i, "c": 101 + i, "v": 1000})
            return {"results": rows}
        if "query1.finance.yahoo.com" in url:
            stamps = [now - (12 - i) * 3600 for i in range(13)]
            q = {
                "open": [200 + i for i in range(13)],
                "high": [202 + i for i in range(13)],
                "low": [199 + i for i in range(13)],
                "close": [201 + i for i in range(13)],
                "volume": [2000] * 13,
            }
            return {"chart": {"result": [{"timestamp": stamps, "indicators": {"quote": [q]}}], "error": None}}
        return None


hub = DeterministicHub()
c = asyncio.run(hub.finnhub_candles("QQQ", "60", now - 86400, now))
check("Yahoo chosen by newest bar timestamp", c.get("_fia_candle_source") == "yahoo_chart_fallback", c.get("_fia_candle_source"))

print("[C] older Yahoo never displaces fresher Polygon")


class PolygonNewerHub(DeterministicHub):
    async def get(self, url, params=None, timeout=10, headers=None):
        if "finnhub.io" in url:
            return None
        if "polygon.io" in url:
            return {"results": [{"t": (now - 1800) * 1000, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10}]}
        if "query1.finance.yahoo.com" in url:
            q = {"open": [1], "high": [2], "low": [0.5], "close": [1.5], "volume": [10]}
            return {"chart": {"result": [{"timestamp": [now - 7200], "indicators": {"quote": [q]}}], "error": None}}
        return None


c2 = asyncio.run(PolygonNewerHub().finnhub_candles("QQQ", "60", now - 86400, now))
check("Polygon retained when newer", c2.get("_fia_candle_source") == "polygon_fallback", c2.get("_fia_candle_source"))

print("[D] downstream completed-bar gate still excludes a forming Yahoo row")
last_forming_start = now - 20 * 60
stamps = [last_forming_start - (12 - i) * 3600 for i in range(13)]
closes = [300 + i for i in range(13)]
payload = {
    "s": "ok",
    "t": stamps,
    "c": closes,
    "o": closes,
    "h": [x + 1 for x in closes],
    "l": [x - 1 for x in closes],
    "v": [100] * 13,
    "_fia_candle_source": "yahoo_chart_fallback",
}


class PayloadHub(ProviderHub):
    async def finnhub_candles(self, *a, **k):
        return payload


st = asyncio.run(PayloadHub().completed_bar_structure("QQQ", "60"))
check("forming final row excluded", st.get("completed_bars") == 12, st.get("completed_bars"))
check("source provenance preserved", st.get("source") == "yahoo_chart_fallback", st.get("source"))

if FAIL:
    print("FAILED", FAIL)
    raise SystemExit(1)
print("ALL LIVE CANDLE FALLBACK / SECURITY REGRESSIONS PASSED")
