"""Phase 05 — FIA probability calibration.

Evaluates whether FIA directional confidence behaves like a real probability.
This module measures the existing model; it does not alter live FIA weights.
"""
from __future__ import annotations
import json, math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

def _f(v: Any) -> Optional[float]:
    try:
        if v is None or v == "": return None
        return float(v)
    except (TypeError, ValueError): return None

def _prob(v: Any) -> Optional[float]:
    x = _f(v)
    if x is None: return None
    if x > 1: x /= 100.0
    return min(1.0, max(0.0, x))

def _prediction(row: Dict[str, Any]) -> Optional[str]:
    bull, bear = _prob(row.get("bullish_probability")), _prob(row.get("bearish_probability"))
    if bull is None and bear is None: return None
    if bull is None: return "bearish"
    if bear is None: return "bullish"
    if bull > bear: return "bullish"
    if bear > bull: return "bearish"
    return None

def _directional_probability(row: Dict[str, Any]) -> Optional[float]:
    bull, bear = _prob(row.get("bullish_probability")), _prob(row.get("bearish_probability"))
    if bull is None and bear is None: return None
    if bull is None: return bear
    if bear is None: return bull
    return max(bull, bear)

def build_samples(predictions: Iterable[Dict[str, Any]], outcomes: Iterable[Dict[str, Any]], horizon: str = "4h") -> List[Dict[str, Any]]:
    pred_by_id = {str(p.get("id") or p.get("prediction_id")): p for p in predictions}
    samples=[]
    for o in outcomes:
        if str(o.get("horizon", "")) != horizon: continue
        p = pred_by_id.get(str(o.get("prediction_id")))
        if not p: continue
        pred, actual, conf = _prediction(p), str(o.get("direction") or "").lower(), _directional_probability(p)
        if pred not in {"bullish","bearish"} or actual not in {"bullish","bearish"} or conf is None: continue
        samples.append({"prediction_id":str(o.get("prediction_id")),"timestamp":p.get("timestamp"),"predicted_direction":pred,"actual_direction":actual,"confidence":conf,"correct":int(pred==actual)})
    return samples

def reliability(samples: Sequence[Dict[str, Any]], bin_edges: Sequence[float]|None=None) -> List[Dict[str, Any]]:
    edges=list(bin_edges or [0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,1.000001])
    groups=[[] for _ in range(len(edges)-1)]
    for s in samples:
        p=float(s["confidence"])
        for i,(lo,hi) in enumerate(zip(edges,edges[1:])):
            if lo <= p < hi or (i==len(edges)-2 and p<=1): groups[i].append(s); break
    rows=[]
    for i,g in enumerate(groups):
        lo,hi=edges[i],edges[i+1]; n=len(g)
        avg=sum(float(x["confidence"]) for x in g)/n if n else None
        acc=sum(int(x["correct"]) for x in g)/n if n else None
        rows.append({"bucket":f"{lo*100:.0f}%+" if i==len(groups)-1 else f"{lo*100:.0f}-{hi*100:.0f}%","count":n,"mean_predicted_probability":avg,"empirical_accuracy":acc,"calibration_gap":(acc-avg) if n else None})
    return rows

def calibration_metrics(samples: Sequence[Dict[str, Any]], bins: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    n=len(samples)
    if not n: return {"samples":0,"ece":None,"mce":None,"brier_score":None,"log_loss":None}
    ece=sum((b["count"]/n)*abs(float(b["calibration_gap"])) for b in bins if b["count"])
    mce=max((abs(float(b["calibration_gap"])) for b in bins if b["count"]),default=0.0)
    brier=sum((float(s["confidence"])-float(s["correct"]))**2 for s in samples)/n
    eps=1e-15
    ll=-sum(math.log(max(eps,min(1-eps,float(s["confidence"])))) if s["correct"] else math.log(max(eps,min(1-eps,1-float(s["confidence"])))) for s in samples)/n
    return {"samples":n,"ece":ece,"mce":mce,"brier_score":brier,"log_loss":ll,"mean_confidence":sum(float(s["confidence"]) for s in samples)/n,"empirical_accuracy":sum(int(s["correct"]) for s in samples)/n}

def analyze(predictions: Iterable[Dict[str, Any]], outcomes: Iterable[Dict[str, Any]], horizons: Sequence[str]=( "4h","8h")) -> Dict[str, Any]:
    predictions=list(predictions); outcomes=list(outcomes); result={"phase":5,"horizons":{}}
    for h in horizons:
        samples=build_samples(predictions,outcomes,h); bins=reliability(samples)
        result["horizons"][h]={"metrics":calibration_metrics(samples,bins),"reliability":bins}
    return result

def write_report(result: Dict[str, Any], path: str|Path) -> Path:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8"); return path
