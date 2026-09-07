from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.schema import validate_analysis

ids={"E0001"}
base={
 "direction":"BULLISH","bullish_probability":61,"bearish_probability":38,
 "confidence":42,"thesis":"test","evidence_ids":["E0001"],"counter_evidence_ids":[],
 "unknowns":[],"failure_conditions":[]
}
ok,err,out=validate_analysis(base,ids)
assert ok,(err,out)
assert round(out["bullish_probability"]+out["bearish_probability"],2)==100.0
assert abs(out["bullish_probability"]-61.6162)<0.05

bad=dict(base); bad["bullish_probability"]=65; bad["bearish_probability"]=30
ok,err,out=validate_analysis(bad,ids)
assert not ok and any("sum to 100" in x for x in err)
print("PASS test_probability_rounding_repair_v6_3")
