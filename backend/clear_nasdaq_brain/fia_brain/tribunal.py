from __future__ import annotations
from typing import Any, Dict, List
from .judge import validate_judge

def combine(judges: List[Dict[str,Any]]) -> Dict[str,Any]:
    if not judges:
        raise ValueError("no judges")
    clean=[validate_judge(x) for x in judges]
    g=sum(x["grounding_score"] for x in clean)/len(clean)
    c=sum(x["causal_score"] for x in clean)/len(clean)
    u=sum(x["uncertainty_score"] for x in clean)/len(clean)
    cap=min(x["recommended_confidence_cap"] for x in clean)
    fatal=[]
    notes=[]
    for x in clean:
        fatal.extend(x["fatal_flags"])
        notes.extend(x["notes"])
    return {
        "judge_count":len(clean),
        "grounding_score":round(g,2),
        "causal_score":round(c,2),
        "uncertainty_score":round(u,2),
        "recommended_confidence_cap":round(cap,2),
        "fatal_flags":sorted(set(map(str,fatal))),
        "notes":list(dict.fromkeys(map(str,notes)))[:20],
    }
