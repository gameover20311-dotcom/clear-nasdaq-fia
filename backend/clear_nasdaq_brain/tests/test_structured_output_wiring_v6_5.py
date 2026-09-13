from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
t=(ROOT/"fia_brain/orchestrator.py").read_text(encoding="utf-8")
assert "response_schema=ANALYSIS_SCHEMA" in t
assert "CAUSAL_SCHEMA" in t and "HYPOTHESIS_SCHEMA" in t and "SCENARIO_SCHEMA" in t
assert "response_schema=JUDGE_SCHEMA" in t
# The structured-output format became provider-conditional when the Groq
# adapter landed (258cd9c), so the literal "'ollama_format':'json_schema'" no
# longer appears anywhere in the orchestrator. The WIRING is intact and now
# covers two providers; only this assertion's spelling was stale. Assert the
# wiring itself, normalised for whitespace, rather than one provider's literal.
n = "".join(t.split())
assert "'ollama_format':" in n and "'json_schema'" in n
assert "'groq_format':" in n and "'json_schema_strict'" in n
assert "'inference_provider':provider" in n
assert "'strict_post_validation':True" in n
assert "'thinking_field_used_as_answer':False" in n
print("PASS test_structured_output_wiring_v6_5")
