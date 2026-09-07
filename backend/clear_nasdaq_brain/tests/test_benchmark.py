from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.benchmark import score_pair
a={"direction":"BULLISH","bullish_probability":60,"bearish_probability":40,"confidence":50,
   "thesis":"macro and tech align","evidence_ids":["E1","E2"],"counter_evidence_ids":["E3"],
   "unknowns":[],"failure_conditions":[]}
s=score_pair(a,a)
assert s["score"]==100.0,s
b=dict(a); b["direction"]="BEARISH"; b["bullish_probability"]=40; b["bearish_probability"]=60
s2=score_pair(b,a)
assert s2["score"]<100
print("PASS test_benchmark")
