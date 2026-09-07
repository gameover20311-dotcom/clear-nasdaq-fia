from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.ensemble import aggregate,divergence
def x(p,d,c=70):
    return {"direction":d,"bullish_probability":p,"bearish_probability":100-p,"confidence":c,
            "evidence_ids":["E1","E2"],"counter_evidence_ids":["E3"],"unknowns":[],"failure_conditions":[],"thesis":"x"}
a=aggregate([x(62,"BULLISH"),x(60,"BULLISH"),x(64,"BULLISH")],{"E1","E2","E3"})
assert a["direction"]=="BULLISH" and a["confidence"]>50
b=aggregate([x(75,"BULLISH"),x(25,"BEARISH"),x(50,"NEUTRAL")],{"E1","E2","E3"})
assert b["direction"] in {"NO_EDGE","NEUTRAL"} and b["confidence"]<70
print("PASS test_ensemble")
