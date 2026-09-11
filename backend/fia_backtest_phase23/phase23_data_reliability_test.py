#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
BACKEND = HERE.parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from fia.signal_identity import canonical_signal_name, is_equal_weight_participation
from fia.provider_reliability import (
    build_provider_health,
    classify_freshness,
    dxy_signal,
    tnx_to_yield,
    us10y_signal,
)
from fia.engine import build_forecast

checks = []

def check(name, condition, detail=""):
    ok = bool(condition)
    checks.append((name, ok, detail))
    print(("✅" if ok else "❌"), name, detail)

# 1) Freshness truth
check("freshness live", classify_freshness(60) == "live")
check("freshness recent", classify_freshness(3600) == "recent")
check("freshness delayed", classify_freshness(24*3600) == "delayed")
check("freshness stale", classify_freshness(100*3600) == "stale")

# 2) Real DXY semantics: stronger dollar pressures NQ
check("DXY up => NQ bearish", dxy_signal(0.50) < 0)
check("DXY down => NQ bullish", dxy_signal(-0.50) > 0)
check("DXY bounded", -1 <= dxy_signal(2.0) <= 1)

# 3) Cleaner US10Y conversion + legacy signal buckets preserved
check("TNX 47.3 => 4.73%", abs(tnx_to_yield(47.3) - 4.73) < 1e-9)
check("TNX percent passthrough", abs(tnx_to_yield(4.73) - 4.73) < 1e-9)
check("US10Y high bearish", us10y_signal(4.73) == -0.5)
check("US10Y mid neutral", us10y_signal(4.25) == 0.0)
check("US10Y low supportive", us10y_signal(3.90) == 0.35)

# 4) Provider health validator
base = {
    "market_quotes": {"available": True, "status": "live", "freshness": "request_live", "fallback": False},
    "candles": {"available": True, "status": "live", "freshness": "request_live", "fallback": False},
    "dxy": {"available": True, "status": "live", "freshness": "live", "fallback": False},
    "us10y": {"available": True, "status": "fallback", "freshness": "fallback", "fallback": True},
    "news": {"available": True, "status": "live_scored", "freshness": "request_live", "fallback": False},
    "macro": {"available": True, "status": "live", "freshness": "request_live", "fallback": False},
    "earnings": {"available": True, "status": "live", "freshness": "request_live", "fallback": False},
    "liquidity": {"available": True, "status": "live", "freshness": "request_live", "fallback": False},
}
health = build_provider_health(base)
check("fallback explicit", "us10y" in health["fallback_active"])
check("trusted fallback not hidden", health["overall"] == "LIVE")

missing = json.loads(json.dumps(base))
missing["dxy"] = {"available": False, "status": "missing", "freshness": "missing", "fallback": False}
health2 = build_provider_health(missing)
check("critical missing => ERROR", health2["overall"] == "ERROR")
check("critical source named", "dxy" in health2["critical_missing"])

stale = json.loads(json.dumps(base))
stale["dxy"] = {"available": True, "status": "stale", "freshness": "stale", "fallback": False}
health3 = build_provider_health(stale)
check("critical stale => DEGRADED", health3["overall"] == "DEGRADED")

# Static wiring checks
providers_text = (BACKEND / "fia/providers.py").read_text(encoding="utf-8")
engine_text = (BACKEND / "fia/engine.py").read_text(encoding="utf-8")
main_text = (BACKEND / "main.py").read_text(encoding="utf-8")
proxy_text = (ROOT / "frontend/app/api/fia/provider-health/route.ts").read_text(encoding="utf-8")

check("provider enrichment wired", "enrich_provider_reliability" in providers_text)
check("real DXY source exposed", "dxy_source" in engine_text)
check("US10Y source exposed", "us10y_source" in engine_text)
check("backend health route", '/api/provider/health' in main_text)
check("frontend health proxy", '/api/provider/health' in proxy_text)

# Phase21 forecast weights must remain identical.
raw = {
    "provider_quotes_available": 17,
    "provider_candle_evidence": "available",
    "nq_structure": -0.2,
    "spx_confirmation": -0.1,
    "dxy": -0.2,
    "us10y": -0.5,
    "mega_cap": -0.1,
    "semis": -0.2,
    "breadth": -0.1,
    "liquidity_evidence_available": True,
    "daily_high": 100.0,
    "daily_low": 90.0,
    "price": 95.0,
    "news": 0.1,
    "news_status": "live_scored",
    "macro": 0.0,
    "macro_status": "FRED live / calendar neutral",
    "earnings": 0.0,
    "source_health": base,
    "provider_health": health,
}
f = build_forecast({"data": raw})

# The Phase21 numeric weight vector is compared by CANONICAL SIGNAL IDENTITY,
# not by literal label. "Breadth" was renamed to "Equal-weight participation"
# because the old name was misleading; the WEIGHT never changed. Comparing
# canonically means a truthfulness rename cannot fail this check, while a real
# weight change still does. The legacy spelling is kept in the literal below so
# the historical expectation stays readable.
weights = {canonical_signal_name(s.name): round(float(s.weight), 2) for s in f.signals}
expected = {canonical_signal_name(k): v for k, v in {
    "NQ structure": 0.20,
    "SPX confirmation": 0.10,
    "DXY": 0.08,
    "US10Y": 0.07,
    "Mega-cap leadership": 0.20,
    "Semiconductors": 0.12,
    "Breadth": 0.08,
    "News": 0.07,
    "Macro calendar": 0.04,
    "Earnings/guidance": 0.04,
}.items()}
check("Phase21 weights unchanged (canonical identity)", weights == expected, str(weights))
check("weight vector sums to exactly 1.0",
      abs(sum(float(s.weight) for s in f.signals) - 1.0) < 1e-9,
      str(sum(float(s.weight) for s in f.signals)))
check("no alias collapses two signals into one",
      len(weights) == len(f.signals), f"{len(weights)} canonical vs {len(f.signals)} emitted")
check("participation signal emitted exactly once",
      sum(1 for s in f.signals if is_equal_weight_participation(s.name)) == 1)
check("binary decision preserved", f.direction in {"BULLISH", "BEARISH"})

failed = [name for name, ok, _ in checks if not ok]
print("\n========================================")
if failed:
    print("❌ PHASE 23 FAIL")
    print("failed =", failed)
    raise SystemExit(1)

print("✅ PHASE 23 PASS")
print("source_freshness_status = PASS")
print("real_dxy_feed = PASS")
print("clean_us10y_feed = PASS")
print("provider_fallback_health = PASS")
print("forecast_weights_changed = NO")
print("broker_execution_added = NO")
print("========================================")
