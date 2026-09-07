from __future__ import annotations
from typing import Any, Dict, List, Set

REQUIRED = {
    "grounding_score","causal_score","uncertainty_score",
    "recommended_confidence_cap","fatal_flags","notes"
}

def validate_judge(obj: Any) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("judge output not object")
    extra=set(obj)-REQUIRED
    if extra: raise ValueError("judge contains unknown fields: "+",".join(sorted(extra)))
    missing = REQUIRED-set(obj)
    if missing:
        raise ValueError("judge missing keys: "+",".join(sorted(missing)))
    out=dict(obj)
    for k in ("grounding_score","causal_score","uncertainty_score","recommended_confidence_cap"):
        v=float(out[k])
        if not 0 <= v <= 100:
            raise ValueError(f"{k} outside [0,100]")
        out[k]=round(v,2)
    if not isinstance(out["fatal_flags"], list):
        raise ValueError("fatal_flags must be list")
    if not isinstance(out["notes"], list):
        raise ValueError("notes must be list")
    out["fatal_flags"]=[str(x)[:200] for x in out["fatal_flags"][:12]]
    out["notes"]=[str(x)[:300] for x in out["notes"][:12]]
    return out

JUDGE_CONTRACT = r"""
Return exactly:
{
 "grounding_score": 0,
 "causal_score": 0,
 "uncertainty_score": 0,
 "recommended_confidence_cap": 0,
 "fatal_flags": [],
 "notes": []
}
"""
