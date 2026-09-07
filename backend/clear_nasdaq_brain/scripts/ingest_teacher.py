#!/usr/bin/env python3
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.cases import read_jsonl,bind_output,upsert_by_case
from fia_brain.parity_v6 import validate_teacher_packet

ap=argparse.ArgumentParser(); ap.add_argument("case_id"); ap.add_argument("json_file")
ap.add_argument("--replace",action="store_true"); a=ap.parse_args()
cases={str(x["case_id"]):x for x in read_jsonl(ROOT/"benchmarks"/"cases.jsonl")}; case=cases.get(a.case_id)
if not case: raise SystemExit("unknown case_id")
split=str(case.get("split","DEV")).upper()
if split=="HOLDOUT":
    if a.replace: raise SystemExit("HOLDOUT teacher replacement is forbidden")
    r=subprocess.run([sys.executable,str(ROOT/"scripts"/"verify_benchmark_seal.py")],cwd=str(ROOT))
    if r.returncode: raise SystemExit("HOLDOUT requires a valid frozen benchmark seal")
obj=json.loads(Path(a.json_file).read_text(encoding="utf-8")); ids={str(x.get("evidence_id")) for x in (case.get("ledger") or {}).get("records",[])}
packet=validate_teacher_packet(obj,ids)
row=bind_output(case,{"final":packet["final"],"reasoning_signature":packet["reasoning_signature"],"status":"REFERENCE","model":"gpt-5.6-sol-reference"},model_label="gpt-5.6-sol-reference")
upsert_by_case(ROOT/"benchmarks"/"sol_reference.jsonl",row,allow_replace=bool(a.replace and split!="HOLDOUT"))
print("ingested",a.case_id,split,row["output_sha256"])
