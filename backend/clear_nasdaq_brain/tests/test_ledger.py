from pathlib import Path
import json, tempfile, sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.ledger import append, verify

with tempfile.TemporaryDirectory() as d:
    p=Path(d)/"x.jsonl"
    append(p,{"a":1}); append(p,{"b":2})
    assert verify(p)["ok"]
    rows=p.read_text().splitlines()
    x=json.loads(rows[0]); x["payload"]["a"]=99
    rows[0]=json.dumps(x)
    p.write_text("\n".join(rows)+"\n")
    assert not verify(p)["ok"]
print("PASS test_ledger")
