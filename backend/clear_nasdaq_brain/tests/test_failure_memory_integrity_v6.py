from pathlib import Path
import tempfile,sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.ledger import append_unique_payload
from fia_brain.failure_memory import digest
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'m.jsonl'; append_unique_payload(p,{'case_id':'x','resolved_at_utc':'2026-01-01T00:00:00+00:00','verdict':{'category':'WRONG_DIRECTION'}})
 rows=p.read_text().splitlines(); o=json.loads(rows[0]); o['payload']['verdict']['category']='CORRECT_DIRECTION'; p.write_text(json.dumps(o)+'\n')
 x=digest(str(p),'2026-06-01T00:00:00+00:00'); assert not x['integrity_ok']
print('PASS test_failure_memory_integrity_v6')
