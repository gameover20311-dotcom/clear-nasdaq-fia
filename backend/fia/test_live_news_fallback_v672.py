"""Regression: stale NewsAPI must not keep News Event AI stale when fresher live news exists.

This is a provider-selection test only. It does not change FIA weights, thresholds,
calibration or the 4H/8H decision rules.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia.providers import ProviderHub  # noqa: E402

FAIL = []

def check(name, cond, detail=""):
    if cond:
        print("  PASS", name)
    else:
        print("  FAIL", name, detail)
        FAIL.append(name)

class FakeHub(ProviderHub):
    def __init__(self, newsapi_articles, finnhub_articles):
        super().__init__()
        self.keys["NEWS_API_KEY"] = "test-news"
        self.keys["FINNHUB_API_KEY"] = "test-finnhub"
        self._newsapi_articles = list(newsapi_articles)
        self._finnhub_articles = list(finnhub_articles)
        self.finnhub_calls = 0

    async def news_sentiment(self, symbol="QQQ"):
        return {"articles": list(self._newsapi_articles)}

    async def finnhub_market_news(self, category="general"):
        self.finnhub_calls += 1
        return list(self._finnhub_articles)

now = datetime.now(timezone.utc)
old = (now - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
fresh = int((now - timedelta(minutes=5)).timestamp())
future = int((now + timedelta(hours=2)).timestamp())

print("[A] stale NewsAPI -> fresher Finnhub market news")
h = FakeHub(
    [{"title":"Nasdaq growth outlook remains mixed", "description":"older item", "publishedAt":old}],
    [{"headline":"Nvidia shares surge as chip demand stays strong", "summary":"fresh market item", "datetime":fresh}],
)
r = asyncio.run(h.live_news_articles())
check("Finnhub selected", r.get("selected_provider") == "Finnhub", str(r))
check("fresh article retained", len(r.get("articles") or []) == 1, str(r))
check("newest evidence is fresh", 0 <= float(r.get("newest_age_seconds")) < 3600, str(r.get("newest_age_seconds")))
check("fallback request was made", h.finnhub_calls == 1, str(h.finnhub_calls))

print("[B] fresh NewsAPI does not spend a Finnhub request")
fresh_iso = (now - timedelta(minutes=4)).isoformat().replace("+00:00", "Z")
h2 = FakeHub(
    [{"title":"Nasdaq tech stocks rally after strong earnings", "description":"fresh", "publishedAt":fresh_iso}],
    [{"headline":"Should not be fetched", "summary":"", "datetime":fresh}],
)
r2 = asyncio.run(h2.live_news_articles())
check("NewsAPI selected", r2.get("selected_provider") == "NewsAPI", str(r2))
check("Finnhub not called", h2.finnhub_calls == 0, str(h2.finnhub_calls))

print("[C] future-dated provider rows are rejected")
h3 = FakeHub(
    [{"title":"old", "description":"", "publishedAt":old}],
    [{"headline":"future provider defect", "summary":"", "datetime":future}],
)
r3 = asyncio.run(h3.live_news_articles())
check("future article not accepted", not (r3.get("articles") or []), str(r3))
check("provider remains unavailable/stale rather than fake-live", r3.get("selected_provider") in ("NewsAPI", None), str(r3))

print("=" * 64)
if FAIL:
    print("FAILED", len(FAIL), "check(s):", FAIL)
    raise SystemExit(1)
print("ALL LIVE NEWS FALLBACK REGRESSIONS PASSED")
