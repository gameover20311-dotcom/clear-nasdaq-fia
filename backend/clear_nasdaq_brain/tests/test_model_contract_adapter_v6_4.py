from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.guardrails import enforce
ids={"E1"}
def obj(b,s,c=70):
    return {"direction":"BULLISH","bullish_probability":b,"bearish_probability":s,"confidence":c,"thesis":"x","evidence_ids":["E1"],"counter_evidence_ids":[],"unknowns":[],"failure_conditions":[]}
a=enforce(obj(.62,.38),ids)
assert a["bullish_probability"]==62.0 and a["bearish_probability"]==38.0
assert a["confidence"]==70.0 and a["validation_meta"]["probability_adapter"]["scale"]=="fraction_to_percent"
b=enforce(obj(65,25),ids)
assert b["bullish_probability"]==70.0 and b["bearish_probability"]==30.0
assert b["confidence"]==60.0
assert b["validation_meta"]["probability_adapter"]["contract_error_points"]==10.0
failed=False
try: enforce(obj(80,80),ids)
except ValueError: failed=True
assert failed
print("PASS test_model_contract_adapter_v6_4")
