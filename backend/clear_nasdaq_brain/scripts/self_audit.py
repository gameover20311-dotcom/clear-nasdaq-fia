#!/usr/bin/env python3
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
sigs=["api"+"."+"openai"+"."+"com","OPENAI"+"_API"+"_KEY","chatgpt"+".com/backend","Authorization"+": Bearer"]
bad=[]; writes=[]
for p in ROOT.rglob("*.py"):
    if "__pycache__" in p.parts or p.resolve()==Path(__file__).resolve(): continue
    text=p.read_text(encoding="utf-8",errors="ignore")
    for s in sigs:
        if s.lower() in text.lower(): bad.append({"file":str(p.relative_to(ROOT)),"signature":s})
    low=text.lower().replace(" ","")
    if "clear_nasdaq_fia-2/backend" in low or ("backend/main.py" in low and ("write_text(" in low or "open(" in low)):
        writes.append(str(p.relative_to(ROOT)))
result={"ok":not bad and not writes,"paid_api_signatures_found":bad,"project_write_risks_found":writes,
        "policy":{"sidecar_only":True,"loopback_only":True,"base_fia_write":False,"forward_oos_write":False,"chatgpt_session_automation":False}}
print(json.dumps(result,indent=2)); raise SystemExit(0 if result["ok"] else 1)
