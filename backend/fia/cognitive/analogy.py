from __future__ import annotations

import csv
import json
import math
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .models import AnalogyView, SpecialistView
from .utils import as_float, parse_dt

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HISTORY = ROOT / "fia_backtest_phase29" / "results" / "phase29_outcome_revalidated_1y.csv"

FEATURE_ORDER = [
    "NQ structure", "SPX confirmation", "DXY", "US10Y", "Mega-cap leadership",
    "Semiconductors", "Breadth", "News", "Macro calendar", "Earnings/guidance",
]


def _parse_signals(row: Dict[str, Any]) -> Dict[str, float]:
    try:
        items = json.loads(row.get("signals_json") or "[]")
    except Exception:
        items = []
    out = {}
    for item in items:
        if not isinstance(item, dict): continue
        name = str(item.get("name") or "")
        value = as_float(item.get("score"))
        freshness = str(item.get("freshness") or "").lower()
        if name and value is not None and freshness not in {"missing","unavailable","error"}:
            # Translate DXY and US10Y into NASDAQ impact direction.
            out[name] = -value if name in {"DXY","US10Y"} else value
    return out


def _vector_from_row(row: Dict[str, Any]) -> List[Optional[float]]:
    m = _parse_signals(row)
    return [m.get(k) for k in FEATURE_ORDER]


def _vector_from_specialists(specialists: Sequence[SpecialistView]) -> List[Optional[float]]:
    mapping = {
        "NQ structure":"Price Structure AI",
        "SPX confirmation":"NQ/ES/SPX Confirmation AI",
        "DXY":"Genuine Dollar/DXY AI",
        "US10Y":"Rates & Yield AI",
        "Mega-cap leadership":"Mega-cap Leadership AI",
        "Semiconductors":"Semiconductor AI",
        "Breadth":"Breadth/Internals AI",
        "News":"News Event AI",
        "Macro calendar":"Macro Surprise AI",
        "Earnings/guidance":"Earnings & Guidance AI",
    }
    by = {s.name:s for s in specialists}
    return [by.get(mapping[k]).score if by.get(mapping[k]) and by[mapping[k]].reliability>0 else None for k in FEATURE_ORDER]


def _similarity(a: Sequence[Optional[float]], b: Sequence[Optional[float]]) -> Tuple[float,int]:
    pairs = [(x,y) for x,y in zip(a,b) if x is not None and y is not None]
    if len(pairs) < 4:
        return 0.0, len(pairs)
    # Distance in [-1,1] feature space; missing dimensions are ignored.
    mse = sum((float(x)-float(y))**2 for x,y in pairs)/len(pairs)
    sim = math.exp(-1.6*mse) * min(1.0, len(pairs)/8.0)
    return max(0.0,min(1.0,sim)), len(pairs)


@lru_cache(maxsize=4)
def load_history(path: str = str(DEFAULT_HISTORY)) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists(): return []
    with p.open(newline="",encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def analogies_for_vector(vector: Sequence[Optional[float]], as_of: Any, horizon: str = "8h",
                         history_path: str = str(DEFAULT_HISTORY), k: int = 15) -> AnalogyView:
    target_dt = parse_dt(as_of)
    if target_dt is None:
        return AnalogyView(False,horizon,None,0,0.0,0.0,reason="invalid as-of timestamp")
    actual_key = f"actual_{horizon}"
    hours = 4 if horizon == "4h" else 8
    candidates = []
    for row in load_history(history_path):
        ts = parse_dt(row.get("timestamp"))
        if ts is None or ts + timedelta(hours=hours) > target_dt:
            continue
        actual = str(row.get(actual_key) or "").upper()
        if actual not in {"BULLISH","BEARISH"}:
            continue
        sim, dims = _similarity(vector,_vector_from_row(row))
        if sim < .35: continue
        candidates.append((sim,dims,row,actual))
    candidates.sort(key=lambda x:x[0],reverse=True)
    top = candidates[:k]
    if len(top) < 5:
        return AnalogyView(False,horizon,None,len(top),0.0,round(sum(x[0] for x in top)/len(top),3) if top else 0.0,
                           nearest=[],reason="fewer than five prior resolved analogues")
    weights = [max(.01,sim**2) for sim,_,_,_ in top]
    bullish = sum(w for w,(_,_,_,actual) in zip(weights,top) if actual=="BULLISH")
    total = sum(weights)
    p = 100*bullish/total if total else None
    ess = (total**2)/sum(w*w for w in weights) if weights else 0.0
    nearest = [{"timestamp":row.get("timestamp"),"similarity":round(sim,3),"shared_dimensions":dims,"actual":actual}
               for sim,dims,row,actual in top[:7]]
    return AnalogyView(True,horizon,round(p,2) if p is not None else None,len(top),round(ess,2),
                       round(sum(x[0] for x in top)/len(top),3),nearest=nearest,
                       reason="Only prior outcomes known by the as-of timestamp are eligible.")


def build_analogy(specialists: Sequence[SpecialistView], as_of: Any, horizon: str = "8h",
                   history_path: str = str(DEFAULT_HISTORY)) -> AnalogyView:
    return analogies_for_vector(_vector_from_specialists(specialists), as_of, horizon, history_path)
