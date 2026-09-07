from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Set, Tuple
from .schema import validate_analysis

def coverage(snapshot: Dict[str,Any]) -> Dict[str,Any]:
    health=snapshot.get("endpoint_health") or {}
    total=len(health); ok=sum(1 for v in health.values() if isinstance(v,dict) and v.get("ok"))
    atomic=str(snapshot.get("atomic_evidence_endpoint") or "")
    atomic_ok=bool((health.get(atomic) or {}).get("ok"))
    return {"endpoints_total":total,"endpoints_ok":ok,"coverage":(ok/total) if total else 0.0,
            "atomic_evidence_ok":atomic_ok,"core_forecast_ok":atomic_ok}

def fail_closed(reason: str,evidence_ids: Optional[List[str]]=None) -> Dict[str,Any]:
    return {"direction":"NO_EDGE","bullish_probability":50.0,"bearish_probability":50.0,"confidence":0.0,
            "thesis":"Fail-closed shadow result: "+reason,"evidence_ids":list(evidence_ids or [])[:6],
            "counter_evidence_ids":[],"unknowns":[reason],
            "failure_conditions":["Re-run only after required evidence/model health is restored."]}

def _finite_num(x: Any) -> float:
    if isinstance(x,bool): raise ValueError("boolean is not numeric")
    v=float(x)
    if not math.isfinite(v): raise ValueError("non-finite numeric")
    return v

def _repair_probability_pair(obj: Any,max_contract_error_points: float=20.0) -> Tuple[Optional[Dict[str,Any]],Optional[Dict[str,Any]]]:
    """Model-boundary adapter only. Strict schema/benchmark validation remains unchanged."""
    if not isinstance(obj,dict): return None,None
    try:
        raw_b=_finite_num(obj.get("bullish_probability")); raw_s=_finite_num(obj.get("bearish_probability")); raw_c=_finite_num(obj.get("confidence"))
    except Exception:
        return None,None
    if not (0 <= raw_b <= 100 and 0 <= raw_s <= 100 and 0 <= raw_c <= 100): return None,None

    b,s=raw_b,raw_s; scale="percent"
    if b <= 1.0 and s <= 1.0 and 0.80 <= (b+s) <= 1.20:
        b*=100.0; s*=100.0; scale="fraction_to_percent"

    err=abs((b+s)-100.0)
    if err > float(max_contract_error_points): return None,None

    repaired_b=max(0.0,min(100.0,(b + (100.0-s))/2.0))
    repaired_s=100.0-repaired_b
    repaired=dict(obj)
    repaired["bullish_probability"]=round(repaired_b,2)
    repaired["bearish_probability"]=round(repaired_s,2)
    penalty=round(err,2)
    repaired["confidence"]=round(max(0.0,raw_c-penalty),2)
    meta={
        "applied":True,
        "scale":scale,
        "raw_bullish_probability":raw_b,
        "raw_bearish_probability":raw_s,
        "contract_error_points":round(err,2),
        "confidence_penalty_points":penalty,
        "method":"symmetric_binary_complement_midpoint",
        "max_contract_error_points":float(max_contract_error_points),
    }
    return repaired,meta

def enforce(obj: Any,valid_ids: Set[str]) -> Dict[str,Any]:
    ok,errors,cleaned=validate_analysis(obj,valid_ids)
    if ok: return cleaned
    if errors == ["probabilities do not sum to 100"]:
        repaired,meta=_repair_probability_pair(obj,20.0)
        if repaired is not None:
            ok2,errors2,cleaned2=validate_analysis(repaired,valid_ids)
            if ok2:
                cleaned2["validation_meta"]={"probability_adapter":meta}
                return cleaned2
            errors=errors2
    raise ValueError("; ".join(errors))
