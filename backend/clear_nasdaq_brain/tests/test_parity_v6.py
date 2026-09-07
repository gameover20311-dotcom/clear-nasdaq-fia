from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.parity_v6 import validate_teacher_packet,score
ids={'E1','E2'}
final={'direction':'BULLISH','bullish_probability':60,'bearish_probability':40,'confidence':55,'thesis':'grounded','evidence_ids':['E1'],'counter_evidence_ids':['E2'],'unknowns':[],'failure_conditions':[]}
p={'final':final,'causal_graph':{'chains':[{'driver':'US10Y','transmission':'US10Y -> valuation -> NQ','polarity':'BULLISH_NQ','strength':70,'evidence_ids':['E1']}]},'hypotheses':{'hypotheses':[{'hypothesis_id':'H1','claim':'rates support','polarity':'BULLISH_NQ','confidence':70,'evidence_for':['E1'],'evidence_against':['E2'],'activation_conditions':[],'invalidation_conditions':[]},{'hypothesis_id':'H2','claim':'breadth fails','polarity':'BEARISH_NQ','confidence':50,'evidence_for':['E2'],'evidence_against':['E1'],'activation_conditions':[],'invalidation_conditions':[]}]},'scenarios':{'worlds':[{'kind':'BULL','probability':50,'narrative':'a','evidence_ids':['E1']},{'kind':'BASE','probability':30,'narrative':'b','evidence_ids':['E2']},{'kind':'BEAR','probability':20,'narrative':'c','evidence_ids':['E2']}]}}
x=validate_teacher_packet(p,ids)['reasoning_signature']; s=score(x,x); assert s['reasoning_score']>99
print('PASS test_parity_v6')
