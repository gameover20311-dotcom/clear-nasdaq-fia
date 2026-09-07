from pathlib import Path
import sys,tempfile,concurrent.futures
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.ledger import append,verify
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/"x.jsonl"
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: list(ex.map(lambda i:append(p,{"i":i}),range(40)))
 v=verify(p); assert v["ok"] and v["rows"]==40,v
print("PASS test_ledger_concurrency")
