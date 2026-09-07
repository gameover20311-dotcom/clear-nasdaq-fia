from pathlib import Path
import tempfile,json,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.benchmark import evaluate
from fia_brain.util import sha256_obj
f={"direction":"BULLISH","bullish_probability":60,"bearish_probability":40,"confidence":50,"thesis":"x","evidence_ids":["E1"],"counter_evidence_ids":[],"unknowns":[],"failure_conditions":[]}
with tempfile.TemporaryDirectory() as d:
 d=Path(d); c={"case_id":"C","split":"DEV","ledger_sha256":"L","ledger":{"ledger_sha256":"L","records":[{"evidence_id":"E1"}]}}; c["case_sha256"]=sha256_obj(c)
 l={"case_id":"C","case_sha256":c["case_sha256"],"ledger_sha256":"L","final":f}; t=json.loads(json.dumps(l)); t["final"]["evidence_ids"]=["BAD"]
 for n,x in (("c",c),("l",l),("t",t)): (d/n).write_text(json.dumps(x)+"\n")
 out=evaluate(d/"l",d/"t",d/"c",None,"DEV"); assert out["paired_cases_valid"]==0 and out["excluded"]
print("PASS test_benchmark_evidence_guard")
