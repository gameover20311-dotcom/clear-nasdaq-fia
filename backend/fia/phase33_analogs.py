from __future__ import annotations
import csv, json, math
from pathlib import Path
from typing import Any, Dict, List
from .phase33_common import dt, fnum

DEFAULT_DB=Path(__file__).resolve().parents[1]/"fia_backtest_phase29"/"results"/"phase29_outcome_revalidated_1y.csv"
CORE=["NQ structure","SPX confirmation","DXY","US10Y","Mega-cap leadership","Semiconductors","Breadth","News"]

def _signals(row:Dict[str,Any])->Dict[str,float]:
    try: arr=json.loads(row.get("signals_json") or "[]")
    except Exception: arr=[]
    return {str(x.get("name")):fnum(x.get("score")) for x in arr if isinstance(x,dict)}
def _vec(row:Dict[str,Any])->List[float]:
    s=_signals(row)
    return [(fnum(row.get("bullish_probability"),50)-50)/50,fnum(row.get("score")),fnum(row.get("confidence"))/100,*[s.get(n,0.0) for n in CORE]]

def nearest_outcome_analogs(timestamp:Any,current:Dict[str,Any],db_path:Path|str=DEFAULT_DB,k:int=7)->Dict[str,Any]:
    p=Path(db_path)
    if not p.exists(): return {"status":"MISSING_NOT_FAKED","neighbors":[]}
    try:
        rows=list(csv.DictReader(p.open(encoding="utf-8")))
    except Exception: return {"status":"ERROR","neighbors":[]}
    cur=dict(current); cv=_vec(cur); t=dt(timestamp); cand=[]
    for r in rows:
        if dt(r.get("timestamp"))>=t: continue
        rv=_vec(r); d=math.sqrt(sum((a-b)**2 for a,b in zip(cv,rv))/len(cv))
        if str(r.get("regime"))==str(cur.get("regime")): d*=0.88
        cand.append((d,r))
    cand.sort(key=lambda x:x[0]); nb=[]
    for d,r in cand[:k]: nb.append({"timestamp":r.get("timestamp"),"distance":round(d,4),"regime":r.get("regime"),"actual_4h":r.get("actual_4h"),"actual_8h":r.get("actual_8h"),"move_4h_pct":r.get("move_4h_pct"),"move_8h_pct":r.get("move_8h_pct")})
    def vote(h):
        vals=[1 if x.get(f"actual_{h}")=="BULLISH" else 0 for x in nb if x.get(f"actual_{h}") in {"BULLISH","BEARISH"}]
        return round(sum(vals)/len(vals),3) if vals else None
    return {"status":"AVAILABLE" if nb else "INSUFFICIENT_HISTORY","neighbors":nb,"observed_bullish_rate_4h":vote("4h"),"observed_bullish_rate_8h":vote("8h"),"point_in_time_only":True}
