from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.causal import validate_causal_graph
x={"chains":[{"driver":"US10Y","transmission":"higher yields -> valuation pressure -> NQ",
"polarity":"BEARISH_NQ","strength":70,"evidence_ids":["E1"]}]}
out=validate_causal_graph(x,{"E1"})
assert out["chains"][0]["polarity"]=="BEARISH_NQ"
bad=False
try:
    validate_causal_graph({"chains":[{"driver":"x","transmission":"y","polarity":"BEARISH_NQ","strength":1,"evidence_ids":["BAD"]}]},{"E1"})
except ValueError: bad=True
assert bad
print("PASS test_causal")
