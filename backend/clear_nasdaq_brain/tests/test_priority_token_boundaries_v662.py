from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.evidence import _priority
assert _priority('metadata.foo') < _priority('live.snapshot.data.meta.foo')
assert _priority('cumulative_volume') < _priority('live.snapshot.data.mu.change_percent')
print('PASS test_priority_token_boundaries_v662')
