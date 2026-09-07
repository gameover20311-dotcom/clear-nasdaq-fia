from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
t=(ROOT/'fia_brain/orchestrator.py').read_text(encoding='utf-8')
assert "'output_budget_resilience'" in t
assert "'trigger':'done_reason=length AND content_chars=0'" in t
assert "env['runtime_events']=list(self._runtime_events)" in t
assert "'strict_validation_after_retry':True" in t
print('PASS test_runtime_event_policy_v6_6')
