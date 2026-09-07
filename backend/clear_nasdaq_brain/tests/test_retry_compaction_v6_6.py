from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.orchestrator import _compact_retry_evidence,_is_output_budget_exhaustion
s='\n'.join(f'E{i} | s | p = value' for i in range(5000))
o=_compact_retry_evidence(s,24000)
assert len(o)<=24000
assert o.splitlines()[0].startswith('E0 |')
assert not o.endswith('val') or len(o)<24000  # line-preserving; no arbitrary fabricated suffix
assert _is_output_budget_exhaustion(RuntimeError('x done_reason=length; content_chars=0'))
assert not _is_output_budget_exhaustion(RuntimeError('done_reason=stop; content_chars=0'))
print('PASS test_retry_compaction_v6_6')
