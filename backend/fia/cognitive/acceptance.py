from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Tuple

from .utils import as_float


def wilson_interval(correct: int, n: int, z: float = 1.96) -> Dict[str,float|None]:
    if n<=0: return {"low":None,"high":None}
    p=correct/n
    denom=1+z*z/n
    center=(p+z*z/(2*n))/denom
    half=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/denom
    return {"low":round(max(0.0,center-half)*100,2),"high":round(min(1.0,center+half)*100,2)}


def directional_metrics(rows: List[Dict[str,Any]], direction_key: str, actual_key: str, probability_key: str) -> Dict[str,Any]:
    resolved=[]
    briers=[]
    logs=[]
    for r in rows:
        a=str(r.get(actual_key) or "").upper(); d=str(r.get(direction_key) or "").upper(); p=as_float(r.get(probability_key))
        if a not in {"BULLISH","BEARISH"} or d not in {"BULLISH","BEARISH"}: continue
        resolved.append(d==a)
        if p is not None:
            q=max(.001,min(.999,p/100.0)); y=1 if a=="BULLISH" else 0
            briers.append((q-y)**2); logs.append(-(y*math.log(q)+(1-y)*math.log(1-q)))
    n=len(resolved); c=sum(resolved)
    return {"n":n,"correct":c,"accuracy":round(100*c/n,2) if n else None,
            "wilson_95":wilson_interval(c,n),"brier":round(sum(briers)/len(briers),4) if briers else None,
            "log_loss":round(sum(logs)/len(logs),4) if logs else None}


def expected_calibration_error(rows: List[Dict[str,Any]], probability_key: str, actual_key: str, bins: int = 8) -> Dict[str,Any]:
    points=[]
    for r in rows:
        p=as_float(r.get(probability_key)); a=str(r.get(actual_key) or "").upper()
        if p is None or a not in {"BULLISH","BEARISH"}: continue
        points.append((p/100.0,1 if a=="BULLISH" else 0))
    if not points: return {"n":0,"ece":None,"bands":[]}
    bands=[]; ece=0.0
    for i in range(bins):
        lo=i/bins; hi=(i+1)/bins
        bucket=[x for x in points if lo<=x[0]<(hi if i<bins-1 else hi+1e-9)]
        if not bucket: continue
        mp=sum(x[0] for x in bucket)/len(bucket); fr=sum(x[1] for x in bucket)/len(bucket)
        ece += len(bucket)/len(points)*abs(mp-fr)
        bands.append({"range":f"{lo:.3f}-{hi:.3f}","n":len(bucket),"mean_probability":round(mp*100,2),"bullish_frequency":round(fr*100,2),"gap":round(abs(mp-fr)*100,2)})
    return {"n":len(points),"ece":round(ece,4),"bands":bands}


def acceptance_report(summary: Dict[str,Any]) -> Dict[str,Any]:
    h=summary.get("holdout",{})
    m8=(h.get("cognitive_8h") or {})
    base8=(h.get("base_8h") or {})
    cal=(h.get("calibration_8h") or {})
    checks={
        "traceable_predictions": bool(summary.get("traceability",{}).get("all_rows_traceable")),
        "no_known_future_leakage": bool(summary.get("integrity",{}).get("no_known_future_leakage")),
        "missing_not_neutral": bool(summary.get("integrity",{}).get("missing_not_neutral")),
        "holdout_sample_present": (m8.get("n") or 0)>=20,
        "holdout_beats_50pct_accuracy": (m8.get("accuracy") or 0)>50.0,
        "holdout_brier_below_naive": (m8.get("brier") or 1.0)<.25,
        "holdout_not_worse_than_base_brier": (m8.get("brier") or 1.0) <= (base8.get("brier") or 1.0),
        "calibration_ece_acceptable": cal.get("ece") is not None and cal.get("ece")<=.10,
    }
    mandatory=["traceable_predictions","no_known_future_leakage","missing_not_neutral","holdout_sample_present"]
    quality=[k for k in checks if k not in mandatory]
    status="PASS" if all(checks[k] for k in mandatory) and sum(checks[k] for k in quality)>=3 else "WITHHELD"
    return {"status":status,"checks":checks,"rule":"Market-grade intelligence claim remains WITHHELD unless integrity gates pass and untouched holdout shows useful probability quality; no accuracy guarantee is implied."}
