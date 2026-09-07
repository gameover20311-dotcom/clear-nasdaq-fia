from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .utils import clamp, logit, sigmoid

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "fia_cognitive_data" / "calibration_model.json"


def fit_platt(probabilities: Iterable[float], labels: Iterable[int], iterations: int = 1200,
              lr: float = .025, l2: float = .015) -> Dict[str, Any]:
    xs, ys = [], []
    for p,y in zip(probabilities,labels):
        try:
            p=float(p); y=int(y)
        except Exception: continue
        if y not in {0,1}: continue
        xs.append(logit(clamp(p/100.0,.01,.99))); ys.append(y)
    if len(xs) < 30:
        return {"available":False,"a":1.0,"b":0.0,"n":len(xs),"reason":"insufficient development sample"}
    a,b=1.0,0.0
    for _ in range(iterations):
        ga=gb=0.0
        for x,y in zip(xs,ys):
            q=sigmoid(a*x+b)
            e=q-y
            ga += e*x; gb += e
        n=len(xs)
        ga=ga/n+l2*(a-1.0); gb=gb/n+l2*b
        a-=lr*ga; b-=lr*gb
    return {"available":True,"a":round(a,8),"b":round(b,8),"n":len(xs),"method":"Platt scaling on logit(probability)","regularization":l2}


def fit_slope_only(probabilities: Iterable[float], labels: Iterable[int], iterations: int = 1200,
                   lr: float = .025, l2: float = .015) -> Dict[str, Any]:
    """Platt scaling with the INTERCEPT PINNED AT ZERO.

    WHY THIS EXISTS
    ---------------
    A full Platt fit learns both a slope (a) and an intercept (b). The intercept
    encodes the unconditional base rate of the DEVELOPMENT window. Injecting that
    into a live directional forecast has two consequences we measured and rejected:

      1. It can move the published probability across 50 and therefore FLIP the
         published direction on evidence that is essentially neutral. With b != 0,
         a raw 50.0 (no information at all) does not map to 50.0.
      2. It transfers a period-specific prior forward. Measured on the untouched
         holdout window, the fitted intercept made Brier WORSE on both horizons
         (4H 0.24322 raw -> 0.25003 calibrated; 8H 0.25805 -> 0.26448), because the
         development window was net bullish and the holdout window was not.

    With b pinned at 0, sigmoid(a*logit(p)) crosses 50 exactly when p crosses 50.
    Calibration can therefore still sharpen (a>1) or shrink (a<1) a probability
    toward or away from 50 -- which is real, useful calibration -- but it can never
    manufacture a direction and can never move a no-information 50.0 off 50.0.
    """
    xs, ys = [], []
    for p, y in zip(probabilities, labels):
        try:
            p = float(p); y = int(y)
        except Exception:
            continue
        if y not in {0, 1}:
            continue
        xs.append(logit(clamp(p / 100.0, .01, .99))); ys.append(y)
    if len(xs) < 30:
        return {"available": False, "a": 1.0, "b": 0.0, "n": len(xs),
                "reason": "insufficient development sample"}
    a = 1.0
    for _ in range(iterations):
        ga = 0.0
        for x, y in zip(xs, ys):
            ga += (sigmoid(a * x) - y) * x
        ga = ga / len(xs) + l2 * (a - 1.0)
        a -= lr * ga
    return {"available": True, "a": round(a, 8), "b": 0.0, "n": len(xs),
            "method": "Platt slope-only (intercept pinned at 0; no base-rate injection)",
            "regularization": l2, "intercept_pinned": True}


def apply_calibration(probability: float, model: Optional[Dict[str,Any]]) -> float:
    p=clamp(float(probability)/100.0,.01,.99)
    if not model or not model.get("available"):
        return round(p*100,3)
    a=float(model.get("a",1.0)); b=float(model.get("b",0.0))
    return round(100*sigmoid(a*logit(p)+b),3)


def save_models(models: Dict[str,Any], path: Path = MODEL_PATH) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(models,indent=2),encoding="utf-8")


def load_models(path: Path = MODEL_PATH) -> Dict[str,Any]:
    if not path.exists(): return {"available":False,"reason":"calibration model not built yet"}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc: return {"available":False,"reason":f"calibration model unreadable: {exc}"}


def calibrate(probability: float, horizon: str = "8h", models: Optional[Dict[str,Any]] = None) -> Dict[str,Any]:
    models=models or load_models()
    model=(models.get("horizons") or {}).get(horizon) if isinstance(models,dict) else None
    calibrated=apply_calibration(probability,model)
    return {"raw_probability":round(float(probability),3),"calibrated_probability":calibrated,
            "horizon":horizon,"model":model or {"available":False,"reason":"no horizon calibration"},
            "dataset_split":models.get("dataset_split") if isinstance(models,dict) else None}


PREMOVE_MODEL_PATH = ROOT / "fia_cognitive_data" / "premove_calibration_model.json"


def load_premove_models(path: Path = PREMOVE_MODEL_PATH) -> Dict[str, Any]:
    """Calibration fitted on PRE-MOVE raw probabilities, slope-only.

    Deliberately separate from the cognitive model: the two layers produce raw
    probabilities from different formulas, and a Platt fit is only valid on the
    score distribution it was fitted on.
    """
    if not path.exists():
        return {"available": False, "reason": "premove calibration model not built yet"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"available": False, "reason": f"premove calibration model unreadable: {exc}"}
