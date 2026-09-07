from __future__ import annotations
import json
import urllib.request

URL = "http://127.0.0.1:8001/api/final/status"
try:
    with urllib.request.urlopen(URL, timeout=60) as r:
        payload = json.loads(r.read().decode())
except Exception as exc:
    raise SystemExit(f"❌ PHASE 27 LIVE CHECK FAIL: {exc}")

print("=== PHASE 27 LIVE FINAL CHECK ===")
print("overall =", payload.get("overall"))
p23 = payload.get("phase23") or {}
p24 = payload.get("phase24") or {}
p25 = payload.get("phase25") or {}
p26 = payload.get("phase26") or {}
print("provider =", (p23.get("provider_health") or {}).get("overall"))
print("provider_score =", (p23.get("provider_health") or {}).get("score"))
print("DXY =", (p23.get("dxy") or {}).get("value"), (p23.get("dxy") or {}).get("source"))
print("US10Y =", (p23.get("us10y") or {}).get("value"), (p23.get("us10y") or {}).get("source"))
print("phase24_grade =", p24.get("setup_grade"))
print("phase25_status =", p25.get("status"), "grade =", p25.get("setup_grade"))
print("phase26_records =", p26.get("records"))
print("checks =", payload.get("checks"))
if payload.get("overall") != "PASS":
    raise SystemExit("❌ PHASE 27 LIVE CHECK DEGRADED")
print("✅ PHASE 27 LIVE HEALTH PASS")
