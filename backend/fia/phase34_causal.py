from __future__ import annotations
from typing import Dict, List, Any
from .phase34_common import f, pearson

def lagged_lead_lag(series:Dict[str,List[float]], target:str='NQ', max_lag:int=6)->Dict[str,Any]:
    y=series.get(target) or []; out=[]
    for name,x in series.items():
        if name==target or len(x)!=len(y) or len(y)<12: continue
        best=None
        for lag in range(1,max_lag+1):
            # x[t-lag] vs target[t]: positive lag means x leads target.
            c=pearson(x[:-lag],y[lag:])
            if c is None: continue
            cand={'lag_bars':lag,'correlation':round(c,4),'abs_correlation':abs(c)}
            if best is None or cand['abs_correlation']>best['abs_correlation']: best=cand
        if best: out.append({'source':name,**best})
    out.sort(key=lambda r:r['abs_correlation'],reverse=True)
    return {'status':'AVAILABLE' if out else 'INSUFFICIENT_HISTORY','leaders':out[:8],'method':'lagged_correlation_research_not_causal_proof'}
