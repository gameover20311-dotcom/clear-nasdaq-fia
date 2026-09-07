from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.evidence import build_ledger

snap={"snapshot_sha256":"abc","payloads":{
 "/api/forecast":{"direction":"BULLISH","bullish_probability":61.2,"nested":{"DXY":"live"}},
 "/api/x":{"noise":[{"v":1},{"v":2}]},
}}
a=build_ledger(snap,max_records=50,max_chars=10000)
b=build_ledger(snap,max_records=50,max_chars=10000)
assert a["ledger_sha256"]==b["ledger_sha256"]
assert len(a["records"])>0
assert len({x["evidence_id"] for x in a["records"]})==len(a["records"])
print("PASS test_evidence")
