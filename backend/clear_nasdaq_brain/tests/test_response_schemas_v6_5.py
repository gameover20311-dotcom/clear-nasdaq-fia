from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.response_schemas import ANALYSIS_SCHEMA,CAUSAL_SCHEMA,HYPOTHESIS_SCHEMA,SCENARIO_SCHEMA,JUDGE_SCHEMA

assert set(ANALYSIS_SCHEMA["required"]) >= {"direction","bullish_probability","bearish_probability","confidence","thesis"}
assert ANALYSIS_SCHEMA["properties"]["direction"]["enum"] == ["BULLISH","BEARISH","NEUTRAL","NO_EDGE"]
assert CAUSAL_SCHEMA["properties"]["chains"]["maxItems"] == 12
assert HYPOTHESIS_SCHEMA["properties"]["hypotheses"]["minItems"] == 2
assert SCENARIO_SCHEMA["properties"]["worlds"]["minItems"] == 3
assert SCENARIO_SCHEMA["properties"]["worlds"]["maxItems"] == 3
assert "recommended_confidence_cap" in JUDGE_SCHEMA["required"]
print("PASS test_response_schemas_v6_5")
