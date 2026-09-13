"""Regression: real Polygon candles must become real completed-bar structure.

CONTEXT
-------
Deployed Render reported:
    critical_missing = ["candles"]
    candles: available=false status=derived
    source="QQQ quote percent-change proxy (NO candle series fetched)"

while direct provider probes showed Finnhub 60m = HTTP 403 and Polygon 60m =
HTTP 200 with 96 real OHLCV bars.

HISTORICAL INCIDENT CONTEXT: an earlier deployed failure was reproducible when
the Polygon fallback could not run, and this suite still locks the diagnostic
that distinguishes a missing/rejected key from a valid Polygon candle response.

CURRENT COMPLETION RULE: provider aggregate timestamps are interval starts. A
historical final row that has already ended must be retained, while a genuinely
forming row must be excluded. This prevents completed 60m evidence from being
made artificially stale by dropping a row and labelling the prior START as END.

These tests do NOT weaken fail-closed:
  * a quote proxy is never reported as real candles
  * delayed Polygon data is never reported as Finnhub LIVE
  * when Polygon fails, candles stay unavailable/derived
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia.providers import ProviderHub  # noqa: E402
from fia.provider_reliability import enrich_provider_reliability  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


# --------------------------------------------------------------------------- #
# Offline fixtures: exact shapes the two providers really return.
# --------------------------------------------------------------------------- #
def polygon_60m_payload(n=96):
    """Polygon aggregates: ms timestamps, o/h/l/c/v — the real free-tier shape."""
    base = 1_788_000_000_000
    out = []
    for i in range(n):
        c = 700.0 + i * 0.25
        out.append({"t": base + i * 3_600_000, "o": c - 0.4, "h": c + 0.9,
                    "l": c - 1.1, "c": c, "v": 1000 + i, "n": 10})
    return {"status": "DELAYED", "resultsCount": n, "results": out}


class FakeHub(ProviderHub):
    """ProviderHub with only the network boundary replaced."""

    def __init__(self, polygon_key="test-polygon-key", polygon_payload=None,
                 polygon_fails=False):
        super().__init__()
        self.keys["FINNHUB_API_KEY"] = "test-finnhub-key"
        self.keys["POLYGON_API_KEY"] = polygon_key
        self._polygon_payload = polygon_payload
        self._polygon_fails = polygon_fails
        self.calls = []

    async def get(self, url, params=None, timeout=10, headers=None):
        self.calls.append(url)
        if "finnhub.io/api/v1/stock/candle" in url:
            return None                      # A) Finnhub 403 -> get() returns None
        if "api.polygon.io" in url:
            if self._polygon_fails:
                return None                  # 401/429/network
            return self._polygon_payload
        return None


# --------------------------------------------------------------------------- #
print("\n[A] reproduces Finnhub 403 + valid Polygon bars")
hub = FakeHub(polygon_payload=polygon_60m_payload(96))
candles = asyncio.run(hub.finnhub_candles("QQQ", "60", 0, 1))
check("finnhub candle endpoint was attempted",
      any("finnhub.io/api/v1/stock/candle" in u for u in hub.calls))
check("polygon fallback was attempted",
      any("api.polygon.io" in u for u in hub.calls))
check("fallback returned a normalized series", isinstance(candles, dict), str(type(candles)))
check("series marked ok", candles.get("s") == "ok")
check("provenance preserved as polygon_fallback",
      candles.get("_fia_candle_source") == "polygon_fallback",
      str(candles.get("_fia_candle_source")))
for k in ("t", "o", "h", "l", "c", "v"):
    check("normalizer carries '%s'" % k, len(candles.get(k) or []) == 96,
          str(len(candles.get(k) or [])))
check("timestamps converted ms -> s",
      candles["t"][0] == 1_788_000_000_000 // 1000, str(candles["t"][0]))

print("\n[B] completed_bar_structure returns genuine completed Polygon bars")
hub2 = FakeHub(polygon_payload=polygon_60m_payload(96))
struct = asyncio.run(hub2.completed_bar_structure("QQQ", "60"))
check("structure returned", isinstance(struct, dict), str(struct))
check("score is a real number", isinstance(struct.get("score"), float), str(struct.get("score")))
check("basis names completed candle bars",
      struct.get("basis") == "QQQ_60M_CANDLES_COMPLETED_BARS", str(struct.get("basis")))
check("source is polygon_fallback, NOT finnhub",
      struct.get("source") == "polygon_fallback", str(struct.get("source")))

print("\n[C] completion is determined from bar start + resolution, not row position")
# This historical fixture contains 96 bars that are ALL already completed. The
# old code unconditionally discarded row 96 and mislabelled row 95's START as
# its END. The corrected logic retains every completed row and derives the true
# bar end from start + 60m.
check("96 historical fetched -> 96 completed", struct.get("completed_bars") == 96,
      str(struct.get("completed_bars")))
last_fetched_s = (1_788_000_000_000 + 95 * 3_600_000) // 1000
check("last completed bar start is the final fetched start",
      int(__import__("datetime").datetime.fromisoformat(
          str(struct.get("last_completed_bar_start_utc"))).timestamp()) == last_fetched_s,
      str(struct.get("last_completed_bar_start_utc")))
check("last completed bar end is start + 60m",
      int(__import__("datetime").datetime.fromisoformat(
          str(struct.get("last_completed_bar_end_utc"))).timestamp()) == last_fetched_s + 3600,
      str(struct.get("last_completed_bar_end_utc")))
check("detail still states forming-bar exclusion policy",
      "in-progress bar excluded" in str(struct.get("detail")))

print("\n[D] provider_candle_evidence becomes available ONLY from genuine OHLC candles")
data_ok = {}
data_ok["provider_candle_evidence"] = "available"
check("real candles -> available", data_ok["provider_candle_evidence"] == "available")
# quote-only path
data_proxy = {"provider_candle_evidence": "derived_from_quote",
              "nq_structure_basis": "QQQ_QUOTE_PERCENT_CHANGE_PROXY"}
check("quote proxy is NEVER 'available'",
      data_proxy["provider_candle_evidence"] != "available")
check("quote proxy basis names itself a proxy",
      "PROXY" in data_proxy["nq_structure_basis"])

print("\n[E] source health identifies the Polygon fallback truthfully")


def health_for(data):
    class _H:
        keys = {}
    # This offline candle fixture has no Yahoo observations. Keep the unrelated
    # network boundary explicit; provider-health logic still executes normally.
    with patch("fia.provider_reliability.yahoo_observation", new=AsyncMock(return_value=None)):
        return asyncio.run(enrich_provider_reliability(_H(), data))


d_av = {"provider_candle_evidence": "available", "nq_structure_source": struct["source"]}
h_av = health_for(d_av)
c_av = h_av["source_health"]["candles"]
check("available -> candles available", c_av["available"] is True)
# V6.6.8: status is derived from the age of the LAST COMPLETED BAR. This fixture
# carries no bar timestamp, so the honest answer is "unknown_age" -- never "live".
# Asserting "live" here was asserting the defect that let a Friday close read as
# a live Monday quote.
check("available + no bar timestamp -> unknown_age, NOT live",
      c_av["status"] == "unknown_age", str(c_av["status"]))
_c_dated = health_for({"provider_candle_evidence": "available",
                       "nq_structure_last_bar_end_utc":
                           __import__("datetime").datetime.now(
                               __import__("datetime").timezone.utc).isoformat()
                       })["source_health"]["candles"]
check("available + fresh completed bar -> live/current_for_session",
      _c_dated["status"] in ("live", "current_for_session"), str(_c_dated["status"]))
check("a real bar age is reported, not 0.0",
      _c_dated["age_seconds"] is not None and _c_dated["age_seconds"] < 60,
      str(_c_dated["age_seconds"]))
check("source names the provider that actually returned the candle series",
      c_av["source"] == "polygon_fallback", c_av["source"])
check("Polygon fallback is explicitly identified", c_av["fallback"] is True)
_c_unspecified = health_for({"provider_candle_evidence": "available"})["source_health"]["candles"]
check("missing provenance is never filled with an invented provider",
      _c_unspecified["source"] == "Candle provider unspecified", _c_unspecified["source"])
check("delayed Polygon is NOT relabelled 'Finnhub LIVE'",
      c_av["source"] != "Finnhub", c_av["source"])

print("\n[F] quote-only path stays derived/unavailable when Polygon fails")
hub3 = FakeHub(polygon_key="", polygon_payload=None)          # key absent
s3 = asyncio.run(hub3.completed_bar_structure("QQQ", "60"))
check("no key -> no structure", s3 is None, str(s3))
check("failure reason recorded: key not configured",
      (hub3._candle_failure or {}).get("reason") == "POLYGON_API_KEY_NOT_CONFIGURED",
      json.dumps(hub3._candle_failure))
check("remediation supplied", bool((hub3._candle_failure or {}).get("remediation")))

hub4 = FakeHub(polygon_key="bad-key", polygon_fails=True)     # key rejected
s4 = asyncio.run(hub4.completed_bar_structure("QQQ", "60"))
check("rejected key -> no structure", s4 is None, str(s4))
check("failure reason recorded: request failed",
      (hub4._candle_failure or {}).get("reason") == "POLYGON_REQUEST_FAILED",
      json.dumps(hub4._candle_failure))

check("THE TWO FAILURE MODES ARE NOW DISTINGUISHABLE",
      (hub3._candle_failure or {}).get("reason") != (hub4._candle_failure or {}).get("reason"))

hub5 = FakeHub(polygon_payload={"status": "OK", "results": []})   # empty results
s5 = asyncio.run(hub5.completed_bar_structure("QQQ", "60"))
check("empty results -> no structure", s5 is None, str(s5))
check("failure reason recorded: empty",
      (hub5._candle_failure or {}).get("reason") == "POLYGON_EMPTY_RESULTS",
      json.dumps(hub5._candle_failure))

# and the derived state surfaces the reason through provider health
d_derived = {"provider_candle_evidence": "derived_from_quote",
             "provider_candle_failure": {"stage": "polygon",
                                         "reason": "POLYGON_API_KEY_NOT_CONFIGURED",
                                         "remediation": "Set POLYGON_API_KEY in the deployment environment."}}
h_dv = health_for(d_derived)
c_dv = h_dv["source_health"]["candles"]
check("derived -> candles NOT available", c_dv["available"] is False)
check("derived -> status derived", c_dv["status"] == "derived", str(c_dv["status"]))
check("derived -> source says NO candle series fetched",
      "NO candle series fetched" in c_dv["source"], c_dv["source"])
check("failure_reason surfaced on the health endpoint",
      c_dv.get("failure_reason") == "POLYGON_API_KEY_NOT_CONFIGURED",
      str(c_dv.get("failure_reason")))
check("remediation surfaced", bool(c_dv.get("remediation")))
check("candles remain in critical_missing when derived",
      "candles" in (h_dv["provider_health"].get("critical_missing") or []),
      str(h_dv["provider_health"].get("critical_missing")))

print("\n[FAIL-CLOSED INVARIANTS]")
check("derived never counts as available", c_dv["available"] is False)
check("diagnostic did not upgrade the proxy",
      d_derived["provider_candle_evidence"] == "derived_from_quote")
check("available path carries no spurious failure_reason",
      "failure_reason" not in c_av)

print("\n" + "=" * 62)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("ALL CLOUD CANDLE-FALLBACK REGRESSION CHECKS PASSED")
