from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
t=(ROOT/"fia_brain/orchestrator.py").read_text(encoding="utf-8")
assert "response_schema=ANALYSIS_SCHEMA" in t
assert "CAUSAL_SCHEMA" in t and "HYPOTHESIS_SCHEMA" in t and "SCENARIO_SCHEMA" in t
assert "response_schema=JUDGE_SCHEMA" in t
assert "'ollama_format':'json_schema'" in t
assert "'thinking_field_used_as_answer':False" in t
print("PASS test_structured_output_wiring_v6_5")
