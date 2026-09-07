#!/usr/bin/env python3
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]; p=ROOT/"benchmarks"/"BENCHMARK_SEAL.json"
if not p.exists(): raise SystemExit("NO SEAL")
seal=json.loads(p.read_text(encoding="utf-8")); bad=[]
for x in seal.get("files",[]):
    f=ROOT/x["path"]; data=f.read_bytes() if f.exists() else b""
    if hashlib.sha256(data).hexdigest()!=x["sha256"] or len(data)!=x["size"]: bad.append(x["path"])
body={k:v for k,v in seal.items() if k!="seal_sha256"}
expected=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest()
if expected!=seal.get("seal_sha256"): bad.append("seal_self_hash")
print("PASS" if not bad else "FAIL "+str(bad)); raise SystemExit(0 if not bad else 1)
