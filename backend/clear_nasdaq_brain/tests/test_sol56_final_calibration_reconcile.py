from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.orchestrator import _reconcile_calibrated_direction
x=_reconcile_calibrated_direction({'direction':'BULLISH','bullish_probability':52,'bearish_probability':48,'confidence':80,'unknowns':[]})
assert x['direction']=='NO_EDGE' and x['confidence']==50,x
assert 'calibration_removed_directional_conviction' in x['unknowns']
y=_reconcile_calibrated_direction({'direction':'BULLISH','bullish_probability':60,'bearish_probability':40,'confidence':80,'unknowns':[]})
assert y['direction']=='BULLISH' and y['confidence']==80,y
print('PASS SOL56 post-calibration coherence')
