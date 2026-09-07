from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional

def load_profile(path: str) -> Optional[Dict[str, Any]]:
    p=Path(path)
    if not p.exists():
        return None
    try:
        x=json.loads(p.read_text(encoding="utf-8"))
        if not x.get("enabled"):
            return None
        if int(x.get("resolved_n",0)) < 30:
            return None
        s=float(x.get("shrink_to_50",0))
        if not 0 <= s <= 1:
            return None
        return x
    except Exception:
        return None

def apply_probability(prob_bull: float, profile: Optional[Dict[str,Any]]) -> float:
    p=float(prob_bull)
    if not profile:
        return p
    s=float(profile.get("shrink_to_50",0))
    return 50.0 + (p-50.0)*(1.0-s)

def apply_confidence(conf: float, profile: Optional[Dict[str,Any]]) -> float:
    if not profile:
        return float(conf)
    cap=float(profile.get("confidence_cap",100))
    return min(float(conf), cap)
