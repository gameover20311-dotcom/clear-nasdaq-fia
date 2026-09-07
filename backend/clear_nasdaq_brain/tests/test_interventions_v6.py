from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.interventions import analyze,confidence_cap
t={'drivers':[{'driver_key':'a','signed_pressure':80,'evidence_ids':['E1']},{'driver_key':'b','signed_pressure':-30,'evidence_ids':['E2']}]} 
x=analyze(t); assert x['fragile_to_single_driver'] and confidence_cap(x)==55
print('PASS test_interventions_v6')
