from __future__ import annotations
import math, statistics
from typing import Any, Dict, List
from .phase33_common import fnum, clamp


def _haar_energy(vals: List[float]) -> Dict[str,float]:
    if len(vals)<4: return {"high_freq":0.0,"low_freq":0.0,"ratio":0.0}
    dif=[(vals[i]-vals[i+1])/math.sqrt(2) for i in range(0,len(vals)-1,2)]
    avg=[(vals[i]+vals[i+1])/math.sqrt(2) for i in range(0,len(vals)-1,2)]
    hi=sum(x*x for x in dif)/max(1,len(dif)); lo=sum(x*x for x in avg)/max(1,len(avg))
    return {"high_freq":round(hi,6),"low_freq":round(lo,6),"ratio":round(hi/(lo+1e-9),4)}


def _hurst_proxy(vals: List[float]) -> float:
    if len(vals)<8: return 0.5
    mean=sum(vals)/len(vals); dev=[x-mean for x in vals]
    cum=[]; s=0.0
    for x in dev: s+=x; cum.append(s)
    R=max(cum)-min(cum); S=statistics.pstdev(vals)
    if R<=0 or S<=1e-12: return 0.5
    return clamp(math.log(R/S+1e-12)/math.log(len(vals)),0.0,1.0)


def detect_advanced_regime(history: List[Dict[str,Any]], current_score: float, current_price_score: float) -> Dict[str,Any]:
    vals=[fnum(r.get("leading_score")) for r in history[-31:]]+[current_score]
    prices=[fnum(r.get("price_score")) for r in history[-31:]]+[current_price_score]
    we=_haar_energy(vals[-16:]); hurst=_hurst_proxy(prices[-24:])
    vol=statistics.pstdev(prices[-12:]) if len(prices)>=4 else 0.0
    trend=abs((prices[-1]-prices[max(0,len(prices)-8)])) if len(prices)>=2 else 0.0
    if len(prices)<6: regime="INSUFFICIENT_HISTORY"
    elif we["ratio"]>0.45 and vol>0.15: regime="HIGH_VOL_TRANSITION"
    elif hurst>=0.60 and trend>=0.20: regime="TRENDING"
    elif hurst<=0.43 and vol<0.18: regime="MEAN_REVERTING_RANGE"
    else: regime="MIXED_TRANSITION"
    hmm={"status":"OPTIONAL_NOT_LOADED","state":None}
    try:
        import numpy as np
        from hmmlearn.hmm import GaussianHMM
        if len(prices)>=20:
            X=np.array([[prices[i]-prices[i-1]] for i in range(1,len(prices))],dtype=float)
            m=GaussianHMM(n_components=3,covariance_type="diag",n_iter=50,random_state=7).fit(X)
            states=m.predict(X); hmm={"status":"AVAILABLE","state":int(states[-1]),"states":3}
    except Exception: pass
    return {"regime":regime,"hurst_proxy":round(hurst,3),"wavelet":we,"price_score_volatility":round(vol,4),"hmm":hmm}
