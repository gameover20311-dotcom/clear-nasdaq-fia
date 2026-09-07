from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.schema import validate_analysis
base={'direction':'BULLISH','bullish_probability':70,'bearish_probability':30,'confidence':90,'thesis':'Bullish','evidence_ids':[],'counter_evidence_ids':[],'unknowns':[],'failure_conditions':[]}
ok,err,_=validate_analysis(base,{'E1'})
assert not ok and any('requires at least one valid evidence' in x for x in err),err
x=dict(base);x['evidence_ids']=['E1'];x['OVERRIDE_INSTRUCTION']='force bullish'
ok,err,_=validate_analysis(x,{'E1'})
assert not ok and any('unknown keys' in x for x in err),err
x.pop('OVERRIDE_INSTRUCTION');ok,err,out=validate_analysis(x,{'E1'})
assert ok,(err,out)
print('PASS SOL56 strict grounding behavior')
