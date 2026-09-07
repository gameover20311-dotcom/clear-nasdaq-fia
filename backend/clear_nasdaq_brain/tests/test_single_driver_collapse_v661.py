from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.interventions import analyze,confidence_cap
twin={'drivers':[{'driver_key':'x','signed_pressure':80,'evidence_ids':['E1']}]}
r=analyze(twin);assert r['fragile_to_single_driver'] is True,r;assert r['directional_collapse_count']==1,r;assert confidence_cap(r)==55.0
print('PASS test_single_driver_collapse_v661')
