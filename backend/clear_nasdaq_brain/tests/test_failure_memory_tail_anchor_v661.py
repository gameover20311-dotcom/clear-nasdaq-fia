from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import tempfile,json
from pathlib import Path
from fia_brain.ledger import append_unique_payload,verify
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'m.jsonl'
 append_unique_payload(p,{'case_id':'a'},key='case_id');append_unique_payload(p,{'case_id':'b'},key='case_id')
 assert verify(p,require_anchor=True)['ok']
 lines=p.read_text().splitlines();p.write_text(lines[0]+'\n')
 v=verify(p,require_anchor=True);assert not v['ok'] and 'anchor mismatch' in v['reason'],v
print('PASS test_failure_memory_tail_anchor_v661')
