from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.evidence_intelligence import freshness_hint
assert freshness_hint({'path':'provider.age_seconds','value':120})=='FRESH'
assert freshness_hint({'path':'provider.age_minutes','value':5})=='FRESH'
assert freshness_hint({'path':'provider.age_minutes','value':20})=='AGING'
assert freshness_hint({'path':'provider.age_minutes','value':120})=='STALE'
assert freshness_hint({'path':'provider.age','value':120})=='UNKNOWN'
print('PASS SOL56 freshness units')
