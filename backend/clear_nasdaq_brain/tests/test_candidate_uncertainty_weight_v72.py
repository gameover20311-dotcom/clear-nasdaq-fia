from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.ensemble import aggregate
valid={'E1','E2','E3'}
cluster={'E1':'C1','E2':'C2','E3':'C3'}
clean={'direction':'BULLISH','bullish_probability':70,'bearish_probability':30,'confidence':80,'evidence_ids':['E1','E2'],'counter_evidence_ids':['E3'],'unknowns':[],'failure_conditions':[]}
uncertain={'direction':'BEARISH','bullish_probability':30,'bearish_probability':70,'confidence':40,'evidence_ids':['E1','E2'],'counter_evidence_ids':['E3'],'unknowns':['u1','u2','u3','u4'],'failure_conditions':['f1','f2']}
r=aggregate([clean,uncertain],valid,cluster)
# The more grounded/high-reliability candidate must have more influence than an equally sourced but uncertain one.
assert r['bullish_probability']>50,r
print('PASS test_candidate_uncertainty_weight_v72')
