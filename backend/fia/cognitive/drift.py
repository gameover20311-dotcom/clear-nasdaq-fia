from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .utils import as_float

ROOT = Path(__file__).resolve().parents[2]
FORWARD = ROOT / "fia_backtest_phase26" / "data" / "forward_predictions.csv"
PHASE30 = ROOT / "fia_backtest_phase30" / "results" / "phase30_cognitive_replay_1y.csv"


def _mean(vals: List[float]) -> float:
    return sum(vals)/len(vals) if vals else 0.0


def _std(vals: List[float]) -> float:
    if len(vals)<2: return 0.0
    m=_mean(vals)
    return math.sqrt(sum((x-m)**2 for x in vals)/(len(vals)-1))


def _load(path: Path) -> List[Dict[str,Any]]:
    if not path.exists(): return []
    try:
        with path.open(newline="",encoding="utf-8") as f: return list(csv.DictReader(f))
    except Exception: return []


def build_drift_status() -> Dict[str,Any]:
    hist=_load(PHASE30)
    live=_load(FORWARD)
    if not hist:
        return {"status":"UNAVAILABLE","reason":"Phase30 reference distribution not built yet","data_drift":None,"model_drift":None}
    ref=[as_float(r.get("calibrated_probability_8h")) for r in hist]
    ref=[x for x in ref if x is not None]
    recent=[as_float(r.get("bullish_probability")) for r in live[-50:]]
    recent=[x for x in recent if x is not None]
    if len(recent)<10:
        return {"status":"BASELINE_ONLY","reference_n":len(ref),"recent_n":len(recent),"reason":"Need at least 10 forward records for live drift comparison"}
    ref_mean,ref_std=_mean(ref),max(_std(ref),1.0)
    recent_mean,recent_std=_mean(recent),_std(recent)
    z=abs(recent_mean-ref_mean)/ref_std
    ratio=recent_std/ref_std if ref_std else 1.0
    data_drift=min(1.0,z/3.0 + abs(math.log(max(.05,ratio)))/4.0)
    status="ALERT" if data_drift>=.65 else "WATCH" if data_drift>=.35 else "STABLE"
    return {"status":status,"reference_n":len(ref),"recent_n":len(recent),
            "reference_probability_mean":round(ref_mean,2),"recent_probability_mean":round(recent_mean,2),
            "reference_std":round(ref_std,2),"recent_std":round(recent_std,2),"data_drift_score":round(data_drift,3),
            "model_drift":"PENDING_OUTCOMES"}
