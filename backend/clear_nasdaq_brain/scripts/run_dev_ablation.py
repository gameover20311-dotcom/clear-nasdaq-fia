#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.config import load
from fia_brain.cases import read_jsonl
from fia_brain.orchestrator import FIABrain
ap=argparse.ArgumentParser(); ap.add_argument('--feature',choices=['market_twin_gate','scenario_entropy_gate','novelty_gate','failure_memory_gate'],required=True); ap.add_argument('--limit',type=int,default=10); ap.add_argument('--split',default='DEV'); a=ap.parse_args()
if a.split.upper()!='DEV': raise SystemExit('Ablation is DEV-only; HOLDOUT/TRAIN forbidden by this tool')
cases=[c for c in read_jsonl(ROOT/'benchmarks/cases.jsonl') if str(c.get('split')).upper()=='DEV'][:max(1,min(a.limit,50))]
base=load(str(ROOT/'config.json')); rows=[]
for c in cases:
    on=dict(base); on[a.feature]=True; off=dict(base); off[a.feature]=False
    A=FIABrain(on).analyze_ledger(c['ledger'],source_quality=c.get('source_quality') or {},write_shadow=False,case_id=c['case_id'],as_of_utc=c.get('captured_at_utc'))
    B=FIABrain(off).analyze_ledger(c['ledger'],source_quality=c.get('source_quality') or {},write_shadow=False,case_id=c['case_id'],as_of_utc=c.get('captured_at_utc'))
    rows.append({'case_id':c['case_id'],'feature':a.feature,'on':A['final'],'off':B['final'],'probability_delta':round(abs(float(A['final']['bullish_probability'])-float(B['final']['bullish_probability'])),2),'confidence_delta':round(abs(float(A['final']['confidence'])-float(B['final']['confidence'])),2)})
print(json.dumps(rows,indent=2,ensure_ascii=False))
