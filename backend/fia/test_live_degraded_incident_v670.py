"""Targeted regression for 2026-09-08 live DATA DEGRADED incident.

Locks two proven code defects only:
1) 60m provider candle timestamps are window starts; a completed final bar must not
   be dropped unconditionally or have its start mislabelled as the bar end.
2) Cognitive Breadth/Internals must read the current BASE signal label
   "Equal-weight participation" (legacy "Breadth" remains compatible).

No network, no secrets, no predictive weights/thresholds are changed or tested here.
"""
from __future__ import annotations

import asyncio
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

# The runtime image used for this forensic test does not ship yfinance.  The
# incident paths below do not call it, so provide an import-only stub rather than
# pretending a live Yahoo request occurred.
if "yfinance" not in sys.modules:
    sys.modules["yfinance"] = types.ModuleType("yfinance")

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia.providers import ProviderHub  # noqa: E402
from fia.cognitive.specialists import build_specialists  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS ", name)
    else:
        print("  FAIL ", name, detail)
        FAILURES.append(name)


class CandleHub(ProviderHub):
    def __init__(self, payload):
        super().__init__()
        self.payload = payload

    async def finnhub_candles(self, symbol, resolution, start_ts, end_ts):
        return self.payload


print("\n[A] completed final delayed-provider bar remains usable")
now = int(time.time())
# Final returned 60m bar started 70m ago and therefore ended 10m ago.  A delayed
# REST feed may legitimately return no still-forming bar.  The old implementation
# dropped this completed final row and then called the previous row's START the
# bar END, making evidence ~130m old and stale against the 90m live ceiling.
last_start = now - 70 * 60
stamps = [last_start - (11 - i) * 3600 for i in range(12)]
closes = [500.0 + i for i in range(12)]
payload = {
    "s": "ok",
    "t": stamps,
    "c": closes,
    "o": [x - 0.5 for x in closes],
    "h": [x + 1.0 for x in closes],
    "l": [x - 1.0 for x in closes],
    "v": [1000.0] * 12,
    "_fia_candle_source": "polygon_fallback",
}
struct = asyncio.run(CandleHub(payload).completed_bar_structure("QQQ", "60"))
check("structure returned", isinstance(struct, dict), repr(struct))
check("all 12 already-completed rows retained", struct.get("completed_bars") == 12,
      str(struct.get("completed_bars")))
end = datetime.fromisoformat(struct["last_completed_bar_end_utc"])
age = (datetime.now(timezone.utc) - end).total_seconds()
check("reported timestamp is the aggregate END, not START", 7 * 60 <= age <= 13 * 60,
      "age_seconds=%r end=%s" % (age, end.isoformat()))
check("start is also preserved for provenance", bool(struct.get("last_completed_bar_start_utc")))

print("\n[B] still-forming final bar is excluded")
forming_start = now - 20 * 60
stamps2 = [forming_start - (12 - i) * 3600 for i in range(13)]
closes2 = [600.0 + i for i in range(13)]
payload2 = dict(payload, t=stamps2, c=closes2,
                o=[x - .5 for x in closes2], h=[x + 1 for x in closes2],
                l=[x - 1 for x in closes2], v=[1000.0] * 13)
struct2 = asyncio.run(CandleHub(payload2).completed_bar_structure("QQQ", "60"))
check("forming row excluded while prior completed rows remain",
      struct2.get("completed_bars") == 12, str(struct2.get("completed_bars")))
check("last completed start is not forming start",
      datetime.fromisoformat(struct2["last_completed_bar_start_utc"]).timestamp() != forming_start)

print("\n[C] current Equal-weight participation feeds Breadth/Internals AI")
forecast = {
    "regime": "BALANCED",
    "signals": [
        {"name": "Equal-weight participation", "score": 0.40, "freshness": "live"},
    ],
}
snapshot = {"data": {"source_health": {"market_quotes": {"age_seconds": 60.0}}}}
views = build_specialists(snapshot, forecast, {"records": []})
by_name = {v.name: v for v in views}
br = by_name["Breadth/Internals AI"]
check("Breadth/Internals no longer permanently MISSING", br.direction != "MISSING", br.to_dict())
check("live positive participation maps bullish", br.direction == "BULLISH", br.to_dict())
check("reason does not falsely claim full-market breadth", "not full-market breadth" in br.reason.lower(), br.reason)

print("\n[D] legacy Breadth packets remain compatible")
legacy = {"regime": "BALANCED", "signals": [{"name": "Breadth", "score": -0.30, "freshness": "live"}]}
views2 = build_specialists(snapshot, legacy, {"records": []})
br2 = {v.name: v for v in views2}["Breadth/Internals AI"]
check("legacy Breadth still works", br2.direction == "BEARISH", br2.to_dict())

print("\n" + "=" * 68)
if FAILURES:
    print("FAILED %d check(s)" % len(FAILURES))
    for f in FAILURES:
        print(" -", f)
    raise SystemExit(1)
print("ALL TARGETED LIVE-DEGRADED INCIDENT REGRESSIONS PASSED")
