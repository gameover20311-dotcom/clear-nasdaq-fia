from __future__ import annotations
import json, math
from pathlib import Path
from typing import Any, Dict, List
from .phase34_common import f
STORE=Path(__file__).resolve().parents[1]/'fia_phase34/data/state_history.jsonl'
KEYS=['lead','price','vix','vxn','us2y','us10y','real_yield','mega','semi','breadth','news','options_skew','gamma']
def vector(state:Dict[str,Any])->List[float|None]:
    return [None if state.get(k) in (None,'') else f(state.get(k)) for k in KEYS]
def nearest(state:Dict[str,Any],k:int=12)->Dict[str,Any]:
    if not STORE.exists(): return {'status':'INSUFFICIENT_HISTORY','neighbors':[],'dimensions':KEYS}
    q=vector(state); rows=[]
    for line in STORE.read_text(encoding='utf-8').splitlines():
        try:r=json.loads(line)
        except Exception:continue
        v=vector(r); pairs=[(a,b) for a,b in zip(q,v) if a is not None and b is not None]
        if len(pairs)<5: continue
        d=math.sqrt(sum((a-b)**2 for a,b in pairs)/len(pairs)); rows.append((d,r,len(pairs)))
    rows.sort(key=lambda x:x[0]); ns=rows[:max(1,k)]
    resolved=[r for _,r,_ in ns if str(r.get('actual_4h','')).upper() in {'BULLISH','BEARISH'}]
    bull=sum(str(r.get('actual_4h','')).upper()=='BULLISH' for r in resolved)
    return {'status':'AVAILABLE' if ns else 'INSUFFICIENT_HISTORY','neighbors':[{'distance':round(d,4),'timestamp':r.get('timestamp'),'actual_4h':r.get('actual_4h'),'dimensions':n} for d,r,n in ns],'observed_bullish_4h':(bull/len(resolved) if resolved else None),'point_in_time_store_required':True}
