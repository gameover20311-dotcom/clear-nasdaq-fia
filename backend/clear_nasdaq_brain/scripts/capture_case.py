#!/usr/bin/env python3
from pathlib import Path
import argparse,sys,uuid,json
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.config import load
from fia_brain.orchestrator import FIABrain
from fia_brain.cases import make_case,append_unique
from fia_brain.evidence import evidence_text
from fia_brain.quality import assess as assess_quality
from fia_brain.evidence_genome import build as build_genome
from fia_brain.parity_v6 import TEACHER_CONTRACT

ap=argparse.ArgumentParser(); ap.add_argument("--count",type=int,default=1)
ap.add_argument("--split",choices=["TRAIN","DEV","HOLDOUT"],default="DEV")
a=ap.parse_args(); cfg=load(str(ROOT/"config.json") if (ROOT/"config.json").exists() else None); brain=FIABrain(cfg)
cases=ROOT/"benchmarks"/"cases.jsonl"; packets=ROOT/"benchmarks"/"teacher_packets"; packets.mkdir(exist_ok=True)
for _ in range(max(1,min(a.count,100))):
    snap,ledger=brain.capture(); q=assess_quality(snap,cfg)
    if not q["ok"]: raise SystemExit("REFUSING CASE CAPTURE: "+json.dumps(q,ensure_ascii=False))
    cid="FIA-"+uuid.uuid4().hex[:12]; case=make_case(cid,a.split,snap,ledger,q,build_genome(ledger)); append_unique(cases,case)
    packet=("CASE_ID="+cid+"\nCASE_SHA256="+case["case_sha256"]+"\nLEDGER_SHA256="+case["ledger_sha256"]+
            "\nSPLIT="+case["split"]+"\nSOURCE_QUALITY="+json.dumps(q,sort_keys=True,ensure_ascii=False)+
            "\nUse only this locked evidence. No browsing.\n"+TEACHER_CONTRACT+"\n\n"+evidence_text(ledger))
    (packets/(cid+".txt")).write_text(packet,encoding="utf-8")
    print(cid,a.split,case["case_sha256"],"quality_cap",q["confidence_cap"])
