"""V6.6.2 regression: gpt-oss:20b identity must be pinnable by DIGEST, not name only.

BEFORE: config.validate() enforced model == "gpt-oss:20b" by NAME. Ollama allows
`ollama cp <any-model> gpt-oss:20b`, so a 0.5B impostor tagged with the expected
name passed every check. OllamaClient.health() already returned model_digest but
no code path ever compared it.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.config import validate, DEFAULTS
from fia_brain.orchestrator import FIABrain
from fia_brain import orchestrator as _orc

REAL="17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7"
IMPOSTOR="dead"*16

base=dict(DEFAULTS); base["shadow_ledger"]=str(ROOT/"data"/"shadow"/"brain_v6.jsonl")
base["calibration_profile"]=str(ROOT/"benchmarks"/"calibration_profile.json")
base["regime_profile"]=str(ROOT/"benchmarks"/"regime_profile.json")
base["failure_memory_ledger"]=str(ROOT/"data"/"memory"/"failure_memory.jsonl")

# --- config validation ---
cfg=validate(dict(base,model_digest_sha256=REAL)); assert cfg["model_digest_sha256"]==REAL
cfg0=validate(dict(base)); assert cfg0["model_digest_sha256"]==""      # empty = name-only, declared
for bad in ("xyz","123",REAL[:-1],REAL.upper()+"a"):
    try:
        validate(dict(base,model_digest_sha256=bad)); raise SystemExit("accepted bad digest %r"%bad)
    except ValueError: pass

class FakeClient:
    def __init__(self,digest): self._d=digest
    def health(self): return {"ok":True,"model_present":True,"expected_model":"gpt-oss:20b",
                              "model_digest":self._d,"models":["gpt-oss:20b"]}

def run(cfg,digest):
    b=FIABrain(cfg); b.client=FakeClient(digest)
    led={"snapshot_sha256":"s","record_count":1,
         "records":[{"source":"/api/dashboard","path":"nq_structure","value":0.1}]}
    from fia_brain.util import sha256_obj
    r=led["records"][0]; body={"source":r["source"],"path":r["path"],"value":r["value"]}
    r["record_hash"]=sha256_obj(body); r["evidence_id"]="E0001"
    led["ledger_sha256"]=sha256_obj({k:v for k,v in led.items() if k!="ledger_sha256"})
    return b.analyze_ledger(led,write_shadow=False)

# pinned + matching digest -> identity verified, not blocked on identity grounds
out=run(validate(dict(base,model_digest_sha256=REAL)),REAL)
assert out["model_identity"]["digest_verified"] is True, out["model_identity"]
assert "model_digest_mismatch" not in str(out.get("error") or "")

# pinned + impostor digest -> FAIL_CLOSED
out=run(validate(dict(base,model_digest_sha256=REAL)),IMPOSTOR)
assert out["status"]=="FAIL_CLOSED", out.get("status")
assert "model_digest_mismatch" in str(out.get("error")), out.get("error")
assert out["final"]["direction"]=="NO_EDGE", out["final"]
assert out["model_identity"]["digest_verified"] is False

# unpinned -> runs, but the payload states plainly that identity is name-only
out=run(validate(dict(base)),IMPOSTOR)
assert out["model_identity"]["digest_pinned"] is False
assert out["model_identity"]["digest_verified"] is False
assert out["model_identity"]["observed_digest"]==IMPOSTOR

# sha256: prefixed digests are handled
out=run(validate(dict(base,model_digest_sha256=REAL)),"sha256:"+REAL)
assert out["model_identity"]["digest_verified"] is True, out["model_identity"]

print("PASS test_model_digest_pin_v662")
