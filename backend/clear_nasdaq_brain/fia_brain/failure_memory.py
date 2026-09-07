from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Dict,List,Optional
from .ledger import append_unique_payload,verify

def _dt(x: str) -> datetime:
    s=str(x)
    if s.endswith('Z'): s=s[:-1]+'+00:00'
    d=datetime.fromisoformat(s)
    if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)

def verdict(final: Dict[str,Any], actual_direction: str) -> Dict[str,Any]:
    pred=str(final.get('direction','NO_EDGE')).upper(); actual=str(actual_direction).upper(); conf=float(final.get('confidence',0))
    correct=pred in {'BULLISH','BEARISH'} and pred==actual
    if pred in {'NO_EDGE','NEUTRAL'}: category='NO_EDGE'
    elif correct: category='CORRECT_DIRECTION'
    elif conf>=70: category='HIGH_CONFIDENCE_WRONG'
    else: category='WRONG_DIRECTION'
    return {'predicted_direction':pred,'actual_direction':actual,'direction_correct':correct,'confidence':round(conf,2),'category':category,
            'causal_correctness':'UNRESOLVED_WITH_DIRECTION_ONLY'}

def record(path: str, case: Dict[str,Any], output: Dict[str,Any], actual_direction: str, resolved_at_utc: str) -> Dict[str,Any]:
    payload={'case_id':case['case_id'],'case_sha256':case.get('case_sha256'),'captured_at_utc':case.get('captured_at_utc'),
             'resolved_at_utc':resolved_at_utc,'genome':case.get('evidence_genome') or {},
             'verdict':verdict(output.get('final',output),actual_direction)}
    append_unique_payload(path,payload,key='case_id'); return payload

def digest(path: str, as_of_utc: str, max_rows: int=300) -> Dict[str,Any]:
    p=Path(path)
    if not p.exists(): return {'eligible_n':0,'categories':{},'high_confidence_wrong_rate':None,'temporal_leakage_blocked':True,'integrity_ok':True}
    if p.stat().st_size>20_000_000: return {'eligible_n':0,'categories':{},'high_confidence_wrong_rate':None,'temporal_leakage_blocked':True,'integrity_ok':False,'reason':'memory_file_too_large'}
    state=verify(p,require_anchor=True)
    if not state.get('ok'): return {'eligible_n':0,'categories':{},'high_confidence_wrong_rate':None,'temporal_leakage_blocked':True,'integrity_ok':False,'reason':'memory_ledger_integrity_failure'}
    cutoff=_dt(as_of_utc); rows=[]
    for line in p.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        row=json.loads(line); payload=row.get('payload') or {}
        try: resolved=_dt(payload.get('resolved_at_utc'))
        except Exception: continue
        if resolved < cutoff: rows.append(payload)
    rows=rows[-max_rows:]; cats={}
    for x in rows:
        c=str((x.get('verdict') or {}).get('category','UNKNOWN')); cats[c]=cats.get(c,0)+1
    wrong=cats.get('HIGH_CONFIDENCE_WRONG',0); directional=sum(v for k,v in cats.items() if k!='NO_EDGE')
    return {'eligible_n':len(rows),'categories':cats,'high_confidence_wrong_rate':round(wrong/max(1,directional),4) if directional else None,
            'temporal_leakage_blocked':True,'integrity_ok':True}

def confidence_cap(d: Dict[str,Any]) -> float:
    n=int(d.get('eligible_n',0)); rate=d.get('high_confidence_wrong_rate')
    if n<30 or rate is None: return 100.0
    if rate>=0.30:return 50.0
    if rate>=0.20:return 65.0
    return 100.0
