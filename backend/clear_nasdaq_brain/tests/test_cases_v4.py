from pathlib import Path
import sys,tempfile
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.cases import append_unique,read_jsonl,make_case
from fia_brain.evidence import build_ledger
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'c.jsonl'; snap={'snapshot_sha256':'S'}; led=build_ledger({'snapshot_sha256':'S','payloads':{'/api/fia/dashboard':{}}},100,10000)
 c=make_case('X','HOLDOUT',snap,led); append_unique(p,c)
 try: append_unique(p,c); raise AssertionError('duplicate accepted')
 except ValueError: pass
 assert len(read_jsonl(p))==1
print('PASS test_cases_v4')
