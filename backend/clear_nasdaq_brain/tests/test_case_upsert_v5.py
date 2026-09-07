from pathlib import Path
import tempfile,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.cases import upsert_by_case,read_jsonl
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/"x.jsonl"; upsert_by_case(p,{"case_id":"C","v":1},False)
 bad=False
 try: upsert_by_case(p,{"case_id":"C","v":2},False)
 except ValueError: bad=True
 assert bad and read_jsonl(p)[0]["v"]==1
 upsert_by_case(p,{"case_id":"C","v":3},True)
 assert read_jsonl(p)[0]["v"]==3
print("PASS test_case_upsert_v5")
