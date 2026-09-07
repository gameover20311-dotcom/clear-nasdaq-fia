from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.config import runtime_policy
f=runtime_policy({'mode':'fast','specialist_timeout_seconds':300,'core_timeout_seconds':480})
b=runtime_policy({'mode':'balanced','specialist_timeout_seconds':300,'core_timeout_seconds':480})
m=runtime_policy({'mode':'max','specialist_timeout_seconds':300,'core_timeout_seconds':480})
assert f['core']['num_ctx']<b['core']['num_ctx']<m['core']['num_ctx']
assert f['core']['num_predict']<b['core']['num_predict']<m['core']['num_predict']
assert m['specialists']['num_ctx']==16384 and m['core']['num_ctx']==24576
# V6.6.2: core output budget raised 3072 -> 8192 after a measured M4/16GB run showed
# CAUSAL_GRAPH exhausting the budget at both 3072 and 4096 with content_chars=0.
assert m['core']['num_predict']==8192
assert m['specialists']['num_predict']==4096
# mode separation must survive the recalibration
assert f['specialists']['num_predict']<b['specialists']['num_predict']<m['specialists']['num_predict']
# V7.4 (measured M4/16GB): reasoning_effort='high' never completed a core/forecast
# stage (0/9 attempts) -- it produced content_chars=0 or timed out, costing 770-900s
# before the ladder rescued it at 'medium'. Mode separation is therefore expressed
# through CONTEXT and EVIDENCE BUDGET, which are the settings that actually change
# what the model can see, not through a setting that yields no output at all.
assert m['core']['num_ctx'] > b['core']['num_ctx'] > f['core']['num_ctx']
assert m['specialists']['max_records'] > b['specialists']['max_records'] > f['specialists']['max_records']
assert m['core']['effort'] in ('medium','high')
print('PASS test_runtime_modes_behavior_v661')
