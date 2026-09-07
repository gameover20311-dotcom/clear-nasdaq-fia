#!/usr/bin/env python3
import json
import urllib.request

BASE = "http:" + "//127.0.0.1:8001"

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode())

try:
    d = get("/api/provider/health")
except Exception as exc:
    print("❌ PHASE 23 LIVE CHECK FAIL: backend/provider-health unavailable ->", exc)
    raise SystemExit(1)

health = d.get("provider_health") or {}
dxy = d.get("dxy") or {}
us10y = d.get("us10y") or {}
print("=== PHASE 23 LIVE PROVIDER CHECK ===")
print("overall =", health.get("overall"))
print("health_score =", health.get("score"))
print("fallback_active =", health.get("fallback_active"))
print("critical_missing =", health.get("critical_missing"))
print("DXY value =", dxy.get("value"))
print("DXY signal =", dxy.get("signal"))
print("DXY source =", dxy.get("source"))
print("US10Y value =", us10y.get("value"))
print("US10Y signal =", us10y.get("signal"))
print("US10Y source =", us10y.get("source"))

if health.get("overall") == "ERROR":
    print("❌ PHASE 23 LIVE HEALTH FAIL")
    raise SystemExit(1)

print("✅ PHASE 23 LIVE HEALTH PASS")
print("direct_dxy_runtime =", "DIRECT" if "Yahoo Finance" in str(dxy.get("source")) else "FALLBACK")
print("us10y_runtime =", "DIRECT" if "Yahoo Finance" in str(us10y.get("source")) else "FALLBACK")
