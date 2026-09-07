#!/usr/bin/env python3
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
targets=[ROOT/"benchmarks"/"cases.jsonl",ROOT/"benchmarks"/"calibration_profile.json",ROOT/"benchmarks"/"regime_profile.json",ROOT/"data"/"memory"/"failure_memory.jsonl",
         ROOT/"config.json",ROOT/"BENCHMARK_GOVERNANCE.md",ROOT/"SOL56_PARITY_PROTOCOL.md"]
targets += sorted((ROOT/"fia_brain").glob("*.py"))
targets += sorted((ROOT/"scripts").glob("*.py"))
# The verifier itself and freeze script are sealed too.
rows=[]
for p in sorted(set(targets),key=lambda x:str(x.relative_to(ROOT))):
    data=p.read_bytes() if p.exists() else b""
    rows.append({"path":str(p.relative_to(ROOT)),"size":len(data),"sha256":hashlib.sha256(data).hexdigest()})
seal={"name":"FIA BRAIN V6 FULL REASONING + STATE + CASE FREEZE","files":rows}
seal["seal_sha256"]=hashlib.sha256(json.dumps(seal,sort_keys=True,separators=(",",":")).encode()).hexdigest()
(ROOT/"benchmarks"/"BENCHMARK_SEAL.json").write_text(json.dumps(seal,indent=2),encoding="utf-8")
print("sealed_files",len(rows)); print("seal_sha256",seal["seal_sha256"])
