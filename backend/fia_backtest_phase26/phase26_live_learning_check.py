#!/usr/bin/env python3
from __future__ import annotations
import json
import urllib.request

BASE = "http:" + "//127.0.0.1:8001"

try:
    with urllib.request.urlopen(BASE + "/api/learning/status", timeout=90) as r:
        d = json.loads(r.read().decode())
except Exception as exc:
    raise SystemExit(f"❌ PHASE 26 LIVE CHECK FAIL: /api/learning/status unavailable -> {exc}")

print("=== PHASE 26 LIVE LEARNING CHECK ===")
print("ok =", d.get("ok"))
print("records =", d.get("records"))
print("pending =", d.get("pending"))
print("validation_status =", (d.get("validation") or {}).get("status"))
print("4h =", (d.get("validation") or {}).get("4h"))
print("8h =", (d.get("validation") or {}).get("8h"))
print("alerts =", d.get("alerts"))
print("forward_only =", (d.get("protections") or {}).get("forward_only"))
print("broker_execution =", (d.get("protections") or {}).get("broker_execution"))

assert d.get("ok") is True
assert (d.get("protections") or {}).get("forward_only") is True
assert (d.get("protections") or {}).get("broker_execution") is False
print("✅ PHASE 26 LIVE CHECK PASS")
