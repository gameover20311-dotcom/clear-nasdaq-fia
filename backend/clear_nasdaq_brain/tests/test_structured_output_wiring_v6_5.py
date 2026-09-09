from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
orch = (ROOT / "fia_brain/orchestrator.py").read_text(encoding="utf-8")
local = (ROOT / "fia_brain/local_llm.py").read_text(encoding="utf-8")

# Orchestrator must pass the real JSON Schemas into every structured call.
assert "response_schema=ANALYSIS_SCHEMA" in orch
assert "CAUSAL_SCHEMA" in orch and "HYPOTHESIS_SCHEMA" in orch and "SCENARIO_SCHEMA" in orch
assert "response_schema=JUDGE_SCHEMA" in orch
assert "response_schema=response_schema" in orch

# Ollama's current API contract accepts the JSON Schema object directly in the
# `format` field. Do not regress to an obsolete internal label/literal check.
assert '"format":response_schema if response_schema is not None else "json"' in local
assert 'if response_schema is not None and not isinstance(response_schema,dict)' in local

# Draft thinking must never be treated as the answer or parsed as output.
assert 'message.get("content")' in local
assert "message.thinking" in local and "Never expose or parse" in local

print("PASS test_structured_output_wiring_v6_5")
