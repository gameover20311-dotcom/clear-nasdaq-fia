#!/usr/bin/env python3
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.benchmark import evaluate
ap=argparse.ArgumentParser(); ap.add_argument("--split",choices=["TRAIN","DEV","HOLDOUT"],default="DEV"); a=ap.parse_args()
if a.split=="HOLDOUT":
    r=subprocess.run([sys.executable,str(ROOT/"scripts"/"verify_benchmark_seal.py")],cwd=str(ROOT))
    if r.returncode: raise SystemExit("HOLDOUT scoring requires valid frozen benchmark seal")
out=evaluate(ROOT/"benchmarks"/"local_outputs.jsonl",ROOT/"benchmarks"/"sol_reference.jsonl",
             ROOT/"benchmarks"/"cases.jsonl",ROOT/"benchmarks"/"outcomes.jsonl",a.split)
print(json.dumps(out,indent=2,ensure_ascii=False))
