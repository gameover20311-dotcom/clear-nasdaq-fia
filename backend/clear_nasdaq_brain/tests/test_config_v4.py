from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.config import validate, DEFAULTS

x=validate(DEFAULTS)
assert x["model"]=="gpt-oss:20b"
assert x["reasoning_effort"]=="high"
assert x["atomic_evidence_endpoint"]=="/api/dashboard"
assert x["health_endpoints"]==["/api/provider/health"]

bad=False
try:
    y=dict(DEFAULTS)
    y["fia_base_url"]="https://example.com"
    validate(y)
except Exception:
    bad=True
assert bad

print("PASS test_config_v4")
