from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.ensemble import aggregate
valid={f'E{i}' for i in range(1,10)}
cands=[
 {'bullish_probability':80,'bearish_probability':20,'confidence':80,'direction':'BULLISH','evidence_ids':[f'E{i}' for i in range(1,9)],'counter_evidence_ids':[],'unknowns':[]},
 {'bullish_probability':20,'bearish_probability':80,'confidence':80,'direction':'BEARISH','evidence_ids':['E9'],'counter_evidence_ids':[],'unknowns':[]},
]
cluster={f'E{i}':'C1' for i in range(1,9)}; cluster['E9']='C2'
x=aggregate(cands,valid,cluster)
assert abs(x['bullish_probability']-50.0)<1e-9,x
print('PASS SOL56 correlation-cluster weighting')
