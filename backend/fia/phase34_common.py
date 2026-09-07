from __future__ import annotations
import hashlib, json, math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

def f(v:Any, default:float=0.0)->float:
    try:
        if v in (None,""): return default
        return float(v)
    except Exception: return default

def clamp(x:float, lo:float=-1.0, hi:float=1.0)->float: return max(lo,min(hi,x))
def utcnow()->str: return datetime.now(timezone.utc).isoformat()
def dt(v:Any)->datetime:
    if isinstance(v,datetime): x=v
    else:
        s=str(v or '').replace('Z','+00:00')
        try: x=datetime.fromisoformat(s)
        except Exception: x=datetime.now(timezone.utc)
    if x.tzinfo is None: x=x.replace(tzinfo=timezone.utc)
    return x.astimezone(timezone.utc)
def raw_snapshot(s:Any)->Dict[str,Any]:
    return s.get('data',{}) if isinstance(s,dict) and isinstance(s.get('data'),dict) else (s if isinstance(s,dict) else {})
def sha(obj:Any)->str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
def missing(name:str, reason:str='source_not_connected')->Dict[str,Any]:
    return {'name':name,'status':'MISSING_NOT_FAKED','value':None,'score':None,'reason':reason}
def pct_change(now:Any, prev:Any)->Optional[float]:
    a,b=f(now,float('nan')),f(prev,float('nan'))
    if a!=a or b!=b or abs(b)<1e-12: return None
    return (a/b-1.0)*100.0
def pearson(a:List[float],b:List[float])->Optional[float]:
    if len(a)!=len(b) or len(a)<5: return None
    ma=sum(a)/len(a); mb=sum(b)/len(b)
    da=[x-ma for x in a]; db=[x-mb for x in b]
    den=math.sqrt(sum(x*x for x in da)*sum(x*x for x in db))
    return None if den<1e-12 else clamp(sum(x*y for x,y in zip(da,db))/den)
