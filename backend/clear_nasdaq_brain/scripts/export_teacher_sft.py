#!/usr/bin/env python3
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
def read(p): return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()] if p.exists() else []
cases={str(x['case_id']):x for x in read(ROOT/'benchmarks/cases.jsonl') if str(x.get('split','')).upper()=='TRAIN'}
sol={str(x['case_id']):x for x in read(ROOT/'benchmarks/sol_reference.jsonl')}; rows=[]
for cid in sorted(set(cases)&set(sol)):
 c=cases[cid]
 if str(sol[cid].get('case_sha256'))!=str(c.get('case_sha256')): continue
 ev='\n'.join(f"{r.get('evidence_id')} | {r.get('source')} | {r.get('path')} = {json.dumps(r.get('value'),ensure_ascii=False)}" for r in (c.get('ledger') or {}).get('records',[]))
 rows.append({'messages':[{'role':'system','content':'CLEAR NASDAQ FIA research analyst. Evidence only. JSON only.'},{'role':'user','content':ev},{'role':'assistant','content':json.dumps(sol[cid].get('final',sol[cid]),sort_keys=True,ensure_ascii=False)}],'metadata':{'case_id':cid,'split':'TRAIN','case_sha256':c.get('case_sha256')}})
out=ROOT/'benchmarks/sol_teacher_sft.jsonl'; out.write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in rows)+('\n' if rows else ''),encoding='utf-8'); print('exported',len(rows))
