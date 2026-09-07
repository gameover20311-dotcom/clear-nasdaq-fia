from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.config import runtime_policy,DEFAULTS
rows=[]
for mode in ('fast','balanced','max'):
    cfg=dict(DEFAULTS);cfg['mode']=mode
    p=runtime_policy(cfg)
    rows.append((p['specialists']['num_ctx'],p['specialists']['num_predict'],p['core']['num_ctx'],p['core']['num_predict']))
assert rows[0][0] < rows[1][0] < rows[2][0],rows
assert rows[0][1] < rows[1][1] < rows[2][1],rows
assert rows[0][2] < rows[1][2] < rows[2][2],rows
assert rows[0][3] < rows[1][3] < rows[2][3],rows
print('PASS SOL56 real mode policy behavior')
