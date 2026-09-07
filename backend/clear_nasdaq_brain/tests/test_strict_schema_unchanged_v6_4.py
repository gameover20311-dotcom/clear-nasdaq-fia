from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.schema import validate_analysis
ids={"E1"}
x={"direction":"BULLISH","bullish_probability":65,"bearish_probability":25,"confidence":70,"thesis":"x","evidence_ids":["E1"],"counter_evidence_ids":[],"unknowns":[],"failure_conditions":[]}
ok,errors,_=validate_analysis(x,ids)
assert not ok and errors==["probabilities do not sum to 100"]
print("PASS test_strict_schema_unchanged_v6_4")
