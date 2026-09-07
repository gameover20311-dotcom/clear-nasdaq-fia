from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.config import runtime_policy
base={'specialist_timeout_seconds':300,'core_timeout_seconds':480,'specialist_max_records':72}
f=runtime_policy({**base,'mode':'fast'}); b=runtime_policy({**base,'mode':'balanced'}); m=runtime_policy({**base,'mode':'max'})
assert f['specialists']['max_records']==36
assert b['specialists']['max_records']==54
assert m['specialists']['max_records']==72
assert f['specialists']['max_records'] < b['specialists']['max_records'] < m['specialists']['max_records']
text=(ROOT/'fia_brain/final_three_brain.py').read_text(encoding='utf-8')
assert 'runtime_policy["specialists"]["max_records"]' in text
print('PASS test_rc2_merge_mode_evidence_budget')
