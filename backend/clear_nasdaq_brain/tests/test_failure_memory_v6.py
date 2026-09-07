from pathlib import Path
import tempfile,sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.ledger import append_unique_payload
from fia_brain.failure_memory import digest
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'m.jsonl'; append_unique_payload(p,{'case_id':'old','resolved_at_utc':'2026-01-01T00:00:00+00:00','verdict':{'category':'HIGH_CONFIDENCE_WRONG'}}); append_unique_payload(p,{'case_id':'future','resolved_at_utc':'2026-12-01T00:00:00+00:00','verdict':{'category':'HIGH_CONFIDENCE_WRONG'}})
 x=digest(str(p),'2026-06-01T00:00:00+00:00'); assert x['eligible_n']==1 and x['temporal_leakage_blocked']
print('PASS test_failure_memory_v6')
