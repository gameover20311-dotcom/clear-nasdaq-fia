"""Regression: durable storage must never be reported as scientific verification."""
from __future__ import annotations
import sys
from pathlib import Path
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from fia.forward_oos_api import _campaign_truth_payload
from fia import forward_oos_durable as dur

def rec(i):
    return {"forecast_id": f"x{i}", "created_at_utc": "2026-09-14T00:00:00+00:00",
            "outcome_4h": "BULLISH", "outcome_8h": "BEARISH"}

durable = {"durability": "DURABLE", "survives_redeploy": True,
           "scientific_artifacts_complete": False,
           "missing_scientific_artifacts": ["evidence:1", "ledger_head:1"]}
bad = {"ok": False, "events": 30, "tamper_evident": False,
       "issues": ["missing_evidence_file:NQ-FOOS-20260909", "missing_ledger_head_anchor"]}
out = _campaign_truth_payload(bad, {}, [rec(i) for i in range(30)], durable, {})
assert out["ok"] is False
assert out["campaign_state"] == "UNVERIFIED"
assert out["storage_state"] == "DURABLE"
assert out["scientifically_countable_n"] == 0
assert out["forward_oos_n"] == 0
assert out["metrics_available"] is False
assert out["milestones"]["reached"] is False
assert out["predictive_edge"] == "NOT_PROVEN"
assert "missing_evidence_file:NQ-FOOS-20260909" in out["verification_issues"]

good = {"ok": True, "events": 30, "tamper_evident": True, "issues": []}
good_durable = {"durability": "DURABLE", "survives_redeploy": True,
                "scientific_artifacts_complete": True}
out2 = _campaign_truth_payload(good, {}, [rec(i) for i in range(30)], good_durable, {})
assert out2["ok"] is True
assert out2["campaign_state"] == "VERIFIED"
assert out2["scientifically_countable_n"] == 30
assert out2["metrics_available"] is True
assert out2["milestones"]["reached"] is True

src = Path(dur.__file__).read_text()
assert "forward_oos_evidence" in src
assert "forward_oos_ledger_heads" in src
assert "Missing old evidence/head artifacts are never synthesized" in src
assert "STORAGE_ONLY_NOT_SCIENTIFIC_VERIFICATION" in src
print("PASS: Forward-OOS storage/proof separation is fail-closed")
