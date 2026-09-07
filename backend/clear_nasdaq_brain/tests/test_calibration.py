from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.calibration import apply_probability,apply_confidence
p={"enabled":True,"resolved_n":50,"shrink_to_50":0.5,"confidence_cap":70}
assert apply_probability(70,p)==60
assert apply_probability(30,p)==40
assert apply_confidence(90,p)==70
print("PASS test_calibration")
