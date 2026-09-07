from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.precommitment import build,verify
m={'market_twin_sha256':'a'}; h={'hypotheses':[{'hypothesis_id':'H1','polarity':'BULLISH_NQ','confidence':60,'evidence_for':['E1'],'evidence_against':[],'activation_conditions':[],'invalidation_conditions':[]}]}; s={'scenario_lattice_sha256':'s','worlds':[]}; i={'intervention_sha256':'i'}
a=build(m,h,s,i); old=a['precommitment_sha256']; assert verify(a)
h['hypotheses'][0]['confidence']=10; b=build(m,h,s,i); assert b['precommitment_sha256']!=old and verify(b)
print('PASS test_precommitment_v6')
