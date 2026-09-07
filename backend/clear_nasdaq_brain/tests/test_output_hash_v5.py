from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.cases import bind_output,valid_output_hash
case={"case_id":"C","case_sha256":"a","ledger_sha256":"b","split":"HOLDOUT"}
row=bind_output(case,{"final":{"x":1},"status":"OK","model":"x"})
assert valid_output_hash(row)
row["final"]["x"]=2
assert not valid_output_hash(row)
print("PASS test_output_hash_v5")
