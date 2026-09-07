#!/usr/bin/env python3
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.config import load
from fia_brain.orchestrator import FIABrain
from fia_brain.cases import read_jsonl,bind_output,upsert_by_case
from fia_brain.parity_v6 import extract_local

ap=argparse.ArgumentParser(); ap.add_argument("--split",choices=["TRAIN","DEV","HOLDOUT"],default="DEV")
ap.add_argument("--overwrite",action="store_true"); a=ap.parse_args()
if a.split=="HOLDOUT":
    if a.overwrite: raise SystemExit("HOLDOUT overwrite is forbidden")
    r=subprocess.run([sys.executable,str(ROOT/"scripts"/"verify_benchmark_seal.py")],cwd=str(ROOT))
    if r.returncode: raise SystemExit("HOLDOUT requires a valid frozen benchmark seal")

cases=[x for x in read_jsonl(ROOT/"benchmarks"/"cases.jsonl") if str(x.get("split","DEV")).upper()==a.split]
outp=ROOT/"benchmarks"/"local_outputs.jsonl"; existing={str(x.get("case_id")):x for x in read_jsonl(outp)}
cfg=load(str(ROOT/"config.json") if (ROOT/"config.json").exists() else None); brain=FIABrain(cfg)
for case in cases:
    cid=str(case["case_id"])
    if cid in existing and not a.overwrite: continue
    result=brain.analyze_ledger(case["ledger"],source_coverage={"locked_case":True},
                                source_quality=case.get("source_quality") or {},
                                write_shadow=False,case_id=cid,as_of_utc=case.get("captured_at_utc"))
    result_for_benchmark=dict(result); result_for_benchmark["reasoning_signature"]=extract_local(result)
    row=bind_output(case,result_for_benchmark,model_label="gpt-oss:20b+fia-v6")
    upsert_by_case(outp,row,allow_replace=bool(a.overwrite and a.split!="HOLDOUT"))
    existing[cid]=row; print(cid,result.get("status"))
    if a.split=="HOLDOUT":
        r=subprocess.run([sys.executable,str(ROOT/"scripts"/"verify_benchmark_seal.py")],cwd=str(ROOT),stdout=subprocess.DEVNULL)
        if r.returncode: raise SystemExit("HOLDOUT state changed during run")
