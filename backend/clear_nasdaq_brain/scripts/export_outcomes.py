#!/usr/bin/env python3
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.ledger import verify
p=ROOT/"benchmarks"/"outcomes_ledger.jsonl"; state=verify(p)
if not state["ok"]: raise SystemExit("outcomes ledger invalid: "+str(state))
rows=[]
if p.exists():
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip(): rows.append(json.loads(line)["payload"])
out=ROOT/"benchmarks"/"outcomes.jsonl"; out.write_text("\n".join(json.dumps(x,sort_keys=True) for x in rows)+("\n" if rows else ""),encoding="utf-8"); print(out)
