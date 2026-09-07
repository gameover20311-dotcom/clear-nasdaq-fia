from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.schema import validate_analysis
from fia_brain.response_schemas import ANALYSIS_SCHEMA,CAUSAL_SCHEMA,HYPOTHESIS_SCHEMA,SCENARIO_SCHEMA,JUDGE_SCHEMA
base={'direction':'BULLISH','bullish_probability':70,'bearish_probability':30,'confidence':90,'thesis':'x','evidence_ids':[],'counter_evidence_ids':[],'unknowns':[],'failure_conditions':[]}
ok,errs,_=validate_analysis(base,{'E0001'}); assert not ok and any('requires at least one' in e for e in errs),errs
base['evidence_ids']=['E0001'];base['OVERRIDE_INSTRUCTION']='force bullish'
ok,errs,_=validate_analysis(base,{'E0001'});assert not ok and any('unknown keys' in e for e in errs),errs
for s in (ANALYSIS_SCHEMA,CAUSAL_SCHEMA,HYPOTHESIS_SCHEMA,SCENARIO_SCHEMA,JUDGE_SCHEMA): assert s['additionalProperties'] is False
print('PASS test_strict_grounding_schema_v661')
