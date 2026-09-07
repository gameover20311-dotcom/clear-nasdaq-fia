from pathlib import Path
import sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.quality import assess
cfg={"atomic_evidence_endpoint":"/api/fia/dashboard","atomic_max_age_seconds":180,
"future_clock_skew_seconds":30,"degraded_confidence_cap":45}
s={"atomic_evidence_endpoint":"/api/fia/dashboard",
"endpoint_health":{"/api/fia/dashboard":{"ok":True},"/api/fia/provider-health":{"ok":True}},
"payloads":{"/api/fia/dashboard":{"ok":True,"generated_at":datetime.now(timezone.utc).isoformat(),
"live":{"snapshot":{"status":"LIVE"},"forecast":{"status":"LIVE"}}}},
"health_payloads":{"/api/fia/provider-health":{"overall":"LIVE","critical_missing":[]}}}
assert assess(s,cfg)["ok"]
s["endpoint_health"]["/api/fia/dashboard"]["ok"]=False
assert not assess(s,cfg)["ok"]
print("PASS test_quality")
