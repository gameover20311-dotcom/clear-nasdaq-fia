from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.invariants import final_invariants
t={"grounding_score":80,"causal_score":70,"uncertainty_score":70}
bad=final_invariants({"direction":"BULLISH","bullish_probability":52,"confidence":70},
                     {"bullish_probability":60},t)
assert "bullish_direction_without_probability_support" in bad
print("PASS test_invariants")
