from pathlib import Path
import sys,tempfile
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.ledger import append,verify

with tempfile.TemporaryDirectory() as d:
    p=Path(d)/'m.jsonl'
    append(p,{'case':'A'}); append(p,{'case':'B'})
    assert verify(p,require_anchor=True)['ok']
    # Delete the latest row, then try to append a replacement. The old RC2
    # append path re-anchored this silently; it must now fail before writing.
    p.write_text(p.read_text(encoding='utf-8').splitlines()[0]+'\n',encoding='utf-8')
    blocked=False
    try:
        append(p,{'case':'C'})
    except RuntimeError as e:
        blocked='anchor mismatch' in str(e)
    assert blocked,'tampered ledger was re-anchored by append'
    assert not verify(p,require_anchor=True)['ok']
    assert len(p.read_text(encoding='utf-8').splitlines())==1
print('PASS test_rc2_merge_ledger_tamper_append')
