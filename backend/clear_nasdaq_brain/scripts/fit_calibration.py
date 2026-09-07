#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]

def read(path):
 p=Path(path); return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()] if p.exists() else []
ap=argparse.ArgumentParser(); ap.add_argument('--cases',default=str(ROOT/'benchmarks/cases.jsonl')); ap.add_argument('--outputs',default=str(ROOT/'benchmarks/local_outputs.jsonl')); ap.add_argument('--out',default=str(ROOT/'benchmarks/calibration_profile.json')); a=ap.parse_args()
cases={str(x['case_id']):x for x in read(a.cases) if str(x.get('split','')).upper()=='TRAIN'}
outs={str(x['case_id']):x for x in read(a.outputs)}; rows=[]
# Outcomes are separate; calibration intentionally cannot use mutable case fields.
outcomes={str(x['case_id']):x for x in read(ROOT/'benchmarks/outcomes.jsonl')}
for cid in sorted(set(cases)&set(outs)&set(outcomes)):
 o=outcomes[cid]
 if str(o.get('case_sha256'))!=str(cases[cid].get('case_sha256')): continue
 direction=str(o.get('outcome_direction','')).upper()
 if direction not in {'BULLISH','BEARISH'}: continue
 f=outs[cid].get('final',outs[cid]); rows.append((float(f['bullish_probability']),1.0 if direction=='BULLISH' else 0.0,float(f['confidence'])))
if len(rows)<30: raise SystemExit('Need >=30 genuinely resolved TRAIN cases; found %d'%len(rows))
def brier(shrink):
 return sum((((50+(p-50)*(1-shrink))/100)-y)**2 for p,y,_ in rows)/len(rows)
grid=[i/100 for i in range(81)]; best=min(grid,key=brier); cs=sorted(c for _,_,c in rows); p90=cs[min(len(cs)-1,int(.9*(len(cs)-1)))]; cap=min(85.0,p90) if len(rows)<100 else min(92.0,p90)
profile={'enabled':True,'resolved_n':len(rows),'training_split':'TRAIN','shrink_to_50':best,'training_brier':round(brier(best),6),'unshrunk_brier':round(brier(0),6),'confidence_cap':round(cap,2),'truth_note':'Fit only on genuinely resolved TRAIN cases. DEV/HOLDOUT are excluded by code.'}
Path(a.out).write_text(json.dumps(profile,indent=2),encoding='utf-8'); print(json.dumps(profile,indent=2))
