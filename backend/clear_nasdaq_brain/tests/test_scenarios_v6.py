from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.scenarios import validate,confidence_cap
x={'worlds':[{'kind':'BULL','probability':33.3,'narrative':'a','evidence_ids':['E1']},{'kind':'BASE','probability':33.4,'narrative':'b','evidence_ids':['E1']},{'kind':'BEAR','probability':33.3,'narrative':'c','evidence_ids':['E1']}]}
y=validate(x,{'E1'}); assert y['entropy']>0.99 and confidence_cap(y)==45
print('PASS test_scenarios_v6')
