"""V6.6.2 regression: the source-quality gate must fail closed on compound and
non-live backend statuses, and on an empty provider-health object.

BEFORE (V6.6.1): BAD_ATOMIC_STATUSES was matched by exact string equality, so the
real backend status 'FINNHUB_ERROR' never equalled 'ERROR' and 'DEMO' was absent
from the set entirely. quality.assess() returned ok=True with zero reasons on a
dashboard carrying no market data at all, and the Brain proceeded to spend ~18
gpt-oss:20b inferences on it.
"""
from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fia_brain.quality import assess, classify_atomic_status, classify_provider_status, status_tokens

NOW = datetime.now(timezone.utc).isoformat()
CFG = {"atomic_evidence_endpoint": "/api/dashboard", "atomic_max_age_seconds": 180,
       "future_clock_skew_seconds": 30, "degraded_confidence_cap": 45}


def snap(snapshot_status="LIVE", forecast_status="LIVE", provider=None,
         generated_at=None, data_as_of=None):
    body = {"ok": True, "generated_at": generated_at or NOW,
            "live": {"snapshot": {"status": snapshot_status},
                     "forecast": {"status": forecast_status}}}
    if data_as_of is not None:
        body["data_as_of"] = data_as_of
    return {"atomic_evidence_endpoint": "/api/dashboard",
            "endpoint_health": {"/api/dashboard": {"ok": True}, "/api/provider/health": {"ok": True}},
            "payloads": {"/api/dashboard": body},
            "health_payloads": {"/api/provider/health":
                                {"overall": "LIVE", "critical_missing": []} if provider is None else provider}}


# --- token classifier ------------------------------------------------------
assert status_tokens("FINNHUB_ERROR") == {"FINNHUB", "ERROR"}
assert status_tokens("") == set()
assert classify_atomic_status("LIVE") == "OK"
assert classify_atomic_status("FINNHUB_ERROR") == "BAD"
assert classify_atomic_status("POLYGON_TIMEOUT_FAILED") == "BAD"
assert classify_atomic_status("YFINANCE-STALE") == "BAD"
assert classify_atomic_status("DEMO") == "NOT_LIVE"
assert classify_atomic_status("SIMULATED_FEED") == "NOT_LIVE"
assert classify_atomic_status("DEGRADED") == "DEGRADED"
assert classify_atomic_status(None) == "OK"
assert classify_provider_status("LIVE") == "OK"
assert classify_provider_status("FINNHUB_ERROR") == "BAD"
assert classify_provider_status("") == "UNKNOWN"

# --- the exact production regression: FINNHUB_ERROR + DEMO + empty provider health ---
q = assess(snap("FINNHUB_ERROR", "DEMO", provider={}), CFG)
assert q["ok"] is False, q
assert any("finnhub_error" in r for r in q["reasons"]), q["reasons"]
assert any("not_live_demo" in r for r in q["reasons"]), q["reasons"]
assert any("provider_health_empty" in r for r in q["reasons"]), q["reasons"]

# each failure mode independently fails closed
assert assess(snap("FINNHUB_ERROR", "LIVE"), CFG)["ok"] is False
assert assess(snap("LIVE", "DEMO"), CFG)["ok"] is False
assert assess(snap("LIVE", "LIVE", provider={}), CFG)["ok"] is False

# healthy input still passes and is not capped
ok = assess(snap("LIVE", "LIVE"), CFG)
assert ok["ok"] is True and ok["confidence_cap"] == 100, ok

# DEGRADED still only caps, it does not fail closed (unchanged V6.6.1 behaviour)
d = assess(snap("DEGRADED", "LIVE"), CFG)
assert d["ok"] is True and d["confidence_cap"] == 45, d

# --- data-age awareness ----------------------------------------------------
# A fresh envelope wrapping a stale market observation must fail closed.
stale = (datetime.now(timezone.utc) - timedelta(seconds=3600)).isoformat()
q = assess(snap("LIVE", "LIVE", generated_at=NOW, data_as_of=stale), CFG)
assert q["ok"] is False, q
assert any("market_observation_too_old" in r for r in q["reasons"]), q["reasons"]
assert q["freshness_basis"] == "market_observation", q

# A fresh observation passes and reports the basis.
fresh = datetime.now(timezone.utc).isoformat()
q = assess(snap("LIVE", "LIVE", generated_at=NOW, data_as_of=fresh), CFG)
assert q["ok"] is True and q["freshness_basis"] == "market_observation", q

# Absent data_as_of degrades to envelope-only and says so explicitly.
q = assess(snap("LIVE", "LIVE"), CFG)
assert q["freshness_basis"] == "response_envelope_only", q
assert any("data_as_of_absent" in w for w in q["warnings"]), q["warnings"]

print("PASS test_source_quality_not_live_v662")
