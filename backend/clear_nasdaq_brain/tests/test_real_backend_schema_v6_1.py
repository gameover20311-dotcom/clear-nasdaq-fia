from pathlib import Path
import sys
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.quality import assess

cfg={
 "atomic_evidence_endpoint":"/api/dashboard",
 "atomic_max_age_seconds":180,
 "future_clock_skew_seconds":30,
 "degraded_confidence_cap":45,
}
snap={
 "atomic_evidence_endpoint":"/api/dashboard",
 "endpoint_health":{
   "/api/dashboard":{"ok":True},
   "/api/provider/health":{"ok":True},
 },
 "payloads":{
   "/api/dashboard":{
     "ok":True,
     "generated_at":datetime.now(timezone.utc).isoformat(),
     "live":{"snapshot":{"data":{"nq_futures_price":29428.5}}}
   }
 },
 "health_payloads":{
   "/api/provider/health":{
     "ok":True,
     "provider_health":{
       "overall":"LIVE",
       "score":66.7,
       "critical_missing":[],
       "missing_sources":["macro","earnings","liquidity"],
     }
   }
 }
}
q=assess(snap,cfg)
assert q["ok"],q
assert q["confidence_cap"]==66.7,q
assert q["provider_score"]==66.7,q
assert set(q["missing_sources"])=={"macro","earnings","liquidity"},q
assert any("provider_missing_sources:" in x for x in q["warnings"]),q
print("PASS test_real_backend_schema_v6_1")
