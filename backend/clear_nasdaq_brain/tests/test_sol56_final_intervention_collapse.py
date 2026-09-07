from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.interventions import analyze,confidence_cap
x=analyze({'drivers':[{'driver_key':'only','signed_pressure':80,'evidence_ids':['E1']}]})
assert x['directional_collapse_count']==1,x
assert x['fragile_to_single_driver'] is True,x
assert confidence_cap(x)==55.0,x
print('PASS SOL56 intervention directional collapse')
