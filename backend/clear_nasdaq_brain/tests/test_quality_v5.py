from pathlib import Path
import sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.quality import assess
now=datetime.now(timezone.utc).isoformat()
cfg={"atomic_evidence_endpoint":"/api/fia/dashboard","atomic_max_age_seconds":180,
"future_clock_skew_seconds":30,"degraded_confidence_cap":45}
base={"atomic_evidence_endpoint":"/api/fia/dashboard",
"endpoint_health":{"/api/fia/dashboard":{"ok":True},"/api/fia/provider-health":{"ok":True}},
"payloads":{"/api/fia/dashboard":{"ok":True,"generated_at":now,"live":{"snapshot":{"status":"LIVE"},"forecast":{"status":"LIVE"}}}},
"health_payloads":{"/api/fia/provider-health":{"overall":"LIVE","critical_missing":[]}}}
q=assess(base,cfg); assert q["ok"] and q["confidence_cap"]==100
base["health_payloads"]["/api/fia/provider-health"]["overall"]="DEGRADED"
q=assess(base,cfg); assert q["ok"] and q["confidence_cap"]==45
base["health_payloads"]["/api/fia/provider-health"]["overall"]="ERROR"
q=assess(base,cfg); assert not q["ok"]
print("PASS test_quality_v5")
