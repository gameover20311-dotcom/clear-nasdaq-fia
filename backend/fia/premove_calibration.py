# CLEAR NASDAQ — FIA Pre-Move forward validation and calibration
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .premove_engine import DEFAULT_HISTORY, _dt, _f

DEFAULT_OUTCOMES = Path(__file__).resolve().parents[1] / "fia_premove" / "data" / "premove_outcomes.jsonl"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            if line.strip(): out.append(json.loads(line))
        except Exception:
            pass
    return out


def brier_score(rows: List[Dict[str, Any]], horizon: str = "4h") -> Optional[float]:
    vals=[]
    for r in rows:
        actual=str(r.get(f"actual_{horizon}") or "").upper()
        p=r.get("premove_bullish_probability")
        if actual not in {"BULLISH","BEARISH"} or p in (None,""):
            continue
        y=1.0 if actual=="BULLISH" else 0.0
        vals.append((_f(p)/100.0-y)**2)
    return round(sum(vals)/len(vals),4) if vals else None


def calibration_bins(rows: List[Dict[str, Any]], horizon: str = "4h") -> List[Dict[str, Any]]:
    out=[]
    for lo,hi in [(0,40),(40,50),(50,60),(60,70),(70,101)]:
        selected=[]
        for r in rows:
            p=r.get("premove_bullish_probability")
            actual=str(r.get(f"actual_{horizon}") or "").upper()
            if p in (None,"") or actual not in {"BULLISH","BEARISH"}: continue
            p=_f(p)
            if lo<=p<hi: selected.append((p,actual))
        if not selected:
            out.append({"band":f"{lo}-{hi}","n":0,"mean_forecast":None,"observed_bullish":None})
            continue
        out.append({
            "band":f"{lo}-{hi}",
            "n":len(selected),
            "mean_forecast":round(sum(p for p,_ in selected)/len(selected),1),
            "observed_bullish":round(100*sum(1 for _,a in selected if a=="BULLISH")/len(selected),1),
        })
    return out


def validation_report(outcomes_path: Path | str = DEFAULT_OUTCOMES) -> Dict[str, Any]:
    rows=_read_jsonl(Path(outcomes_path))
    resolved4=[r for r in rows if str(r.get("actual_4h") or "").upper() in {"BULLISH","BEARISH"}]
    resolved8=[r for r in rows if str(r.get("actual_8h") or "").upper() in {"BULLISH","BEARISH"}]
    def accuracy(rs,h):
        if not rs: return None
        good=0
        for r in rs:
            pred="BULLISH" if _f(r.get("premove_bullish_probability"),50)>=50 else "BEARISH"
            good += pred==str(r.get(f"actual_{h}") or "").upper()
        return round(100*good/len(rs),2)
    sufficient=min(len(resolved4),len(resolved8))>=100
    return {
        "ok":True,
        "status":"CALIBRATED_ENOUGH_FOR_RESEARCH" if sufficient else "COLLECTING_FORWARD_EVIDENCE",
        "resolved_4h":len(resolved4),
        "resolved_8h":len(resolved8),
        "directional_accuracy_4h":accuracy(resolved4,"4h"),
        "directional_accuracy_8h":accuracy(resolved8,"8h"),
        "brier_4h":brier_score(rows,"4h"),
        "brier_8h":brier_score(rows,"8h"),
        "calibration_4h":calibration_bins(rows,"4h"),
        "calibration_8h":calibration_bins(rows,"8h"),
        "minimum_recommended_resolved_samples":100,
        "claim_policy":"Never label the pre-move probability calibrated until sufficient forward-only resolved samples exist.",
    }
