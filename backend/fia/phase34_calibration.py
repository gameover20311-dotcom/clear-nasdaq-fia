from __future__ import annotations
import json, math
from pathlib import Path
from typing import Any, Dict, List, Tuple
from .phase34_common import f, clamp
MODEL=Path(__file__).resolve().parents[1]/'fia_phase34/data/calibration.json'
def _sig(x): return 1/(1+math.exp(-max(-30,min(30,x))))
def fit_platt(rows:List[Dict[str,Any]],xkey='score',ykey='y',steps=1500,lr=.03)->Dict[str,Any]:
    xs=[]; ys=[]
    for r in rows:
        if r.get(xkey) in (None,'') or r.get(ykey) not in (0,1,False,True): continue
        xs.append(f(r[xkey])); ys.append(1.0 if bool(r[ykey]) else 0.0)
    if len(xs)<100: return {'approved':False,'reason':'MIN_100_DEVELOPMENT_SAMPLES','n':len(xs)}
    a=b=0.0
    for _ in range(steps):
        ga=gb=0.0
        for x,y in zip(xs,ys):
            p=_sig(a*x+b); ga+=(p-y)*x; gb+=p-y
        a-=lr*ga/len(xs); b-=lr*gb/len(xs)
    return {'approved':False,'candidate':True,'method':'PLATT','a':a,'b':b,'n':len(xs),'note':'Candidate must pass untouched OOS before approved=true.'}
def apply(score:float)->Dict[str,Any]:
    if not MODEL.exists(): return {'status':'NOT_CALIBRATED','probability':None}
    try:m=json.loads(MODEL.read_text())
    except Exception:return {'status':'MODEL_INVALID','probability':None}
    if not m.get('approved'): return {'status':'OOS_NOT_APPROVED','probability':None,'model_version':m.get('version')}
    p=_sig(f(m.get('a'))*score+f(m.get('b')))
    return {'status':'OOS_CALIBRATED','probability':round(100*p,1),'model_version':m.get('version')}
def brier(ps,ys): return sum((p-y)**2 for p,y in zip(ps,ys))/len(ps) if ps else None
def logloss(ps,ys):
    if not ps:return None
    return -sum(y*math.log(max(1e-9,p))+(1-y)*math.log(max(1e-9,1-p)) for p,y in zip(ps,ys))/len(ps)
