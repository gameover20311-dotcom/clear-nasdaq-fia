from __future__ import annotations
from typing import Any, Dict, List

def final_invariants(final: Dict[str,Any], consensus: Dict[str,Any], tribunal: Dict[str,Any]) -> List[str]:
    fail=[]
    p=float(final.get("bullish_probability",50))
    c=float(final.get("confidence",0))
    direction=str(final.get("direction",""))
    if direction=="BULLISH" and p < 55:
        fail.append("bullish_direction_without_probability_support")
    if direction=="BEARISH" and p > 45:
        fail.append("bearish_direction_without_probability_support")
    if direction in {"NEUTRAL","NO_EDGE"} and c > 75:
        fail.append("neutral_no_edge_confidence_too_high")
    if tribunal["grounding_score"] < 65:
        fail.append("tribunal_grounding_below_65")
    if tribunal["causal_score"] < 55:
        fail.append("tribunal_causal_below_55")
    if tribunal["uncertainty_score"] < 55:
        fail.append("tribunal_uncertainty_handling_below_55")
    if abs(p-float(consensus.get("bullish_probability",50))) > 20:
        fail.append("final_too_far_from_independent_consensus")
    return fail
