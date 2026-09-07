from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.config import load,runtime_policy
cfg=load(str(ROOT/'config.json'))
assert cfg['num_ctx']==24576
# V6.6.2 (measured on M4/16GB): the CAUSAL_GRAPH stage times out on real evidence at
# 96 fact cards (10909 ch, >900s) and at 40 (4925 ch, >600s), but completes at 24
# (3243 ch) in 359.2s. The core evidence budget is a HARDWARE constraint, not a taste.
assert cfg['max_fact_cards']==24
assert cfg['specialist_max_records']==72
assert cfg['specialist_timeout_seconds']==600  # V6.6.2: 300s timed out a real specialist on M4/16GB
assert cfg['core_timeout_seconds']==900   # V6.6.2: CAUSAL_GRAPH exceeded 480s twice on real evidence
p=runtime_policy(cfg)
assert p['mode']=='max'
assert p['specialists']['effort']=='medium' and p['specialists']['num_ctx']==16384 and p['specialists']['num_predict']==4096
# V7.4 (measured): first-attempt effort is 'medium'; 'high' never completed a
# core stage on M4/16GB. Context and output budget are unchanged.
assert p['core']['effort']=='medium' and p['core']['num_ctx']==24576 and p['core']['num_predict']==8192
assert p['critics']['num_ctx']==16384 and p['forecast']['num_ctx']==24576
print('PASS test_runtime_policy_v6_2')
