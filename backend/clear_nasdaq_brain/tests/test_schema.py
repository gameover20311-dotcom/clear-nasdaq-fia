from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.schema import validate_analysis

ids={"E0001","E0002"}
good={"direction":"BULLISH","bullish_probability":60,"bearish_probability":40,"confidence":55,
      "thesis":"Evidence-grounded research thesis.","evidence_ids":["E0001"],
      "counter_evidence_ids":["E0002"],"unknowns":[],"failure_conditions":["regime change"]}
ok,err,_=validate_analysis(good,ids); assert ok,err
bad=dict(good); bad["evidence_ids"]=["E9999"]
ok,err,_=validate_analysis(bad,ids); assert not ok and any("unknown evidence" in x for x in err)
bad=dict(good); bad["bearish_probability"]=50
ok,err,_=validate_analysis(bad,ids); assert not ok and any("sum" in x for x in err)
print("PASS test_schema")
