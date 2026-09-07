from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.tribunal import combine
j=lambda g,c,u,cap:{"grounding_score":g,"causal_score":c,"uncertainty_score":u,
"recommended_confidence_cap":cap,"fatal_flags":[],"notes":[]}
x=combine([j(80,70,75,72),j(90,80,70,65),j(85,75,80,68)])
assert x["judge_count"]==3 and x["recommended_confidence_cap"]==65
print("PASS test_tribunal")
