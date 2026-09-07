from pathlib import Path
import tempfile,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.ledger import append_unique_payload,verify
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/"o.jsonl"; append_unique_payload(p,{"case_id":"C","outcome_direction":"BULLISH"})
 bad=False
 try: append_unique_payload(p,{"case_id":"C","outcome_direction":"BEARISH"})
 except ValueError: bad=True
 assert bad and verify(p)["ok"]
print("PASS test_outcome_unique_v5")
