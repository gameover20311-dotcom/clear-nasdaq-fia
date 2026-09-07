from pathlib import Path
from tempfile import TemporaryDirectory
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.ledger import append,verify,_anchor_path

with TemporaryDirectory() as d:
    p=Path(d)/'ledger.jsonl'
    append(p,{'id':'A'}); append(p,{'id':'B'})
    assert verify(p,require_anchor=True).get('ok')
    # Attacker deletes the loss/tail AND the external head anchor.
    p.write_text(p.read_text().splitlines()[0]+'\n',encoding='utf-8')
    _anchor_path(p).unlink()
    assert not verify(p,require_anchor=True).get('ok')
    try:
        append(p,{'id':'C'})
    except RuntimeError as e:
        assert 'anchor missing' in str(e).lower(),e
    else:
        raise AssertionError('tampered unanchored chain was silently re-anchored')
print('PASS test_sol56_anchor_deletion_bypass_v661')
