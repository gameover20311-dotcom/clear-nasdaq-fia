from __future__ import annotations
from typing import Any, Dict
from .phase34_common import raw_snapshot, f, clamp
DIRECTION={'CPI':-1,'CORE_CPI':-1,'PCE':-1,'CORE_PCE':-1,'NFP':1,'UNEMPLOYMENT':-1,'GDP':1,'ISM':1,'EARNINGS':1,'GUIDANCE':1}
def analyze_event_surprise(snapshot:Any)->Dict[str,Any]:
    raw=raw_snapshot(snapshot); ev=raw.get('event') or raw.get('macro_event') or raw.get('catalyst')
    if not isinstance(ev,dict): return {'status':'MISSING_NOT_FAKED','score':None}
    name=str(ev.get('type',ev.get('name','UNKNOWN'))).upper().replace(' ','_'); actual=ev.get('actual'); expected=ev.get('expected',ev.get('consensus'))
    if actual in (None,'') or expected in (None,''): return {'status':'AVAILABLE_NO_SURPRISE','event':name,'score':None,'actual':actual,'expected':expected}
    scale=max(abs(f(expected)),abs(f(ev.get('historical_std'))),1e-6); raw_sur=(f(actual)-f(expected))/scale
    sign=DIRECTION.get(name,0); score=clamp(raw_sur*sign) if sign else None
    return {'status':'AVAILABLE','event':name,'actual':f(actual),'expected':f(expected),'standardized_surprise':round(raw_sur,4),'nasdaq_directional_score':round(score,4) if score is not None else None,'mapping_requires_event_semantics':sign==0}
