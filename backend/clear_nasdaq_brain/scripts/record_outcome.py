#!/usr/bin/env python3
from pathlib import Path
import argparse,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.cases import read_jsonl
from fia_brain.ledger import append_unique_payload
ap=argparse.ArgumentParser(); ap.add_argument("case_id"); ap.add_argument("outcome",choices=["BULLISH","BEARISH"])
a=ap.parse_args(); cases={str(x["case_id"]):x for x in read_jsonl(ROOT/"benchmarks"/"cases.jsonl")}; c=cases.get(a.case_id)
if not c: raise SystemExit("unknown case")
row={"case_id":c["case_id"],"case_sha256":c["case_sha256"],"outcome_direction":a.outcome}
append_unique_payload(ROOT/"benchmarks"/"outcomes_ledger.jsonl",row,key="case_id")
print("recorded immutable outcome",a.case_id,a.outcome)
