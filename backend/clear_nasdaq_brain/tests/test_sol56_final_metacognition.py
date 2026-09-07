from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.metacognition import assess
x=assess({'probability_spread_std':30},{'grounding_score':70,'causal_score':60,'uncertainty_score':50},{'entropy':.95},{'enabled':True,'novelty_score':4},{'high_confidence_wrong_rate':.2},{'fragile_to_single_driver':True},{'confidence_cap':45})
assert x['high_uncertainty'] and x['confidence_cap']<60,x
y=assess({'probability_spread_std':1},{'grounding_score':95,'causal_score':95,'uncertainty_score':95},{'entropy':.2},{'enabled':False},{'high_confidence_wrong_rate':0.0},{'fragile_to_single_driver':False},{'confidence_cap':100})
assert y['confidence_cap']>80,y
print('PASS SOL56 metacognitive uncertainty')
