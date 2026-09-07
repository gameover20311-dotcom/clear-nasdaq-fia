#!/usr/bin/env python3
from __future__ import annotations
import json
import urllib.request

BASE = "http:" + "//127.0.0.1:8001"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=45) as r:
        return json.loads(r.read().decode())

try:
    d = get("/api/accuracy")
except Exception as exc:
    raise SystemExit(f"❌ PHASE 24 LIVE CHECK FAIL: /api/accuracy unavailable -> {exc}")

print("=== PHASE 24 LIVE ACCURACY CHECK ===")
print("setup_grade =", d.get("setup_grade"))
print("research_eligible =", d.get("research_eligible"))
print("direction =", d.get("direction"))
print("regime =", (d.get("regime_policy") or {}).get("regime"))
print("confidence =", (d.get("confidence_gate") or {}).get("confidence"))
print("confidence_band =", (d.get("confidence_gate") or {}).get("band"))
print("evidence_agreement =", (d.get("evidence") or {}).get("agreement"))
print("evidence_conflict =", (d.get("evidence") or {}).get("conflict"))
print("catalyst_status =", (d.get("catalyst") or {}).get("status"))

assert d.get("ok") is True
assert d.get("setup_grade") in {"A++", "A+", "A", "WATCH", "NO_TRADE"}
assert 0.0 <= float((d.get("evidence") or {}).get("agreement", 0)) <= 1.0
assert 0.0 <= float((d.get("evidence") or {}).get("conflict", 0)) <= 1.0
assert (d.get("frozen_core") or {}).get("forecast_weights_changed") is False
print("✅ PHASE 24 LIVE CHECK PASS")
