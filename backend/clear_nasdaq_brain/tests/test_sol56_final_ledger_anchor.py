from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from pathlib import Path
from tempfile import TemporaryDirectory
from fia_brain.ledger import append,verify
with TemporaryDirectory() as td:
 p=Path(td)/'x.jsonl'
 append(p,{'x':1}); append(p,{'x':2})
 assert verify(p)['ok']
 lines=p.read_text().splitlines(); p.write_text(lines[0]+'\n')
 q=verify(p)
 assert not q['ok'] and 'anchor mismatch' in q['reason'],q
 try: append(p,{'x':3})
 except RuntimeError: pass
 else: raise AssertionError('append after tail deletion must be blocked')
print('PASS SOL56 ledger head anchor')
