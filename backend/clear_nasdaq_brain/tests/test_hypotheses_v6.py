from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.hypotheses import validate,pressure
x={'hypotheses':[{'hypothesis_id':'H1','claim':'rates help','polarity':'BULLISH_NQ','confidence':70,'evidence_for':['E1'],'evidence_against':['E2'],'activation_conditions':[],'invalidation_conditions':[]},{'hypothesis_id':'H2','claim':'breadth weak','polarity':'BEARISH_NQ','confidence':60,'evidence_for':['E2'],'evidence_against':['E1'],'activation_conditions':[],'invalidation_conditions':[]}]}
y=validate(x,{'E1','E2'}); assert len(y['hypotheses'])==2 and abs(pressure(y)['signed_pressure'])<0.2
print('PASS test_hypotheses_v6')
