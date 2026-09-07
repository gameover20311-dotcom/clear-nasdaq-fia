from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.probability_forge import forge
chief={'direction':'NO_EDGE','bullish_probability':50,'bearish_probability':50,'confidence':45,'thesis':'x','evidence_ids':['E1','E2'],'counter_evidence_ids':['E3'],'unknowns':[],'failure_conditions':[]}
cons={'direction':'BULLISH','bullish_probability':75,'bearish_probability':25,'confidence':80,'probability_spread_std':3}
sc={'worlds':[{'kind':'BULL','probability':75},{'kind':'BASE','probability':15},{'kind':'BEAR','probability':10}],'entropy':.4}
tri={'grounding_score':95,'causal_score':95,'uncertainty_score':95,'recommended_confidence_cap':90}
x,p=forge(chief,cons,sc,tri,{'overall_uncertainty':5,'confidence_cap':95},{'fragile_to_single_driver':False},{'confidence_cap':95},{'E1':'C1','E2':'C2','E3':'C3'},None)
assert x['direction']=='NO_EDGE',x
assert p['policy']['may_create_new_direction'] is False
print('PASS test_probability_forge_no_direction_creation_v72')
