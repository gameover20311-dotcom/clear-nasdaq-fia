#!/usr/bin/env python3
from __future__ import annotations
import json
import urllib.request

BASE = "http:" + "//127.0.0.1:8001"

payload = {
    "chart_analysis": {
        "direction": "BEARISH",
        "htf_poi": {"type": "supply", "direction": "BEARISH"},
        "order_blocks": [{"direction": "BEARISH"}],
        "fair_value_gaps": [{"direction": "BEARISH"}],
        "liquidity_sweeps": [{"side": "BUY-SIDE", "reaction": "BEARISH REJECTION"}],
        "smt": {"detected": True, "direction": "BEARISH", "pair": "ES"},
        "session_context": {"session": "NEW_YORK", "direction": "BEARISH"},
        "execution_confirmation": {"timeframe": "1m", "direction": "BEARISH"},
    }
}

req = urllib.request.Request(
    BASE + "/api/confluence",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode())
except Exception as exc:
    raise SystemExit(f"❌ PHASE 25 LIVE CHECK FAIL: /api/confluence unavailable -> {exc}")

print("=== PHASE 25 LIVE CONFLUENCE CHECK ===")
print("setup_grade =", d.get("setup_grade"))
print("research_eligible =", d.get("research_eligible"))
print("confluence_score =", d.get("confluence_score"))
print("completeness =", d.get("confluence_completeness"))
print("alignment =", d.get("confluence_alignment"))
print("phase24_grade =", d.get("phase24_setup_grade"))
print("missing_evidence =", d.get("missing_evidence"))

assert d.get("ok") is True
assert d.get("setup_grade") in {"A++", "A+", "A", "WATCH", "NO_TRADE"}
assert (d.get("frozen_core") or {}).get("forecast_weights_changed") is False
assert (d.get("frozen_core") or {}).get("broker_execution_added") is False
print("✅ PHASE 25 LIVE CHECK PASS")
