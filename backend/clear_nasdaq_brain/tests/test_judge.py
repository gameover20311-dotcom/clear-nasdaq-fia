from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.judge import validate_judge
x=validate_judge({"grounding_score":80,"causal_score":75,"uncertainty_score":70,
"recommended_confidence_cap":68,"fatal_flags":[],"notes":["ok"]})
assert x["recommended_confidence_cap"]==68
bad=False
try: validate_judge({"grounding_score":101,"causal_score":75,"uncertainty_score":70,
"recommended_confidence_cap":68,"fatal_flags":[],"notes":[]})
except ValueError: bad=True
assert bad
print("PASS test_judge")
