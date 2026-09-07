from __future__ import annotations
from typing import Any, Dict, List

VALID_POLARITY = {"BULLISH_NQ","BEARISH_NQ","MIXED","UNKNOWN"}

def validate_causal_graph(obj: Any, valid_ids: set) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("causal graph must be object")
    if set(obj)!={"chains"}: raise ValueError("causal graph contains unknown top-level fields")
    chains = obj.get("chains")
    if not isinstance(chains, list):
        raise ValueError("chains must be list")
    out = []
    for c in chains[:12]:
        if not isinstance(c, dict):
            raise ValueError("chain item must be object")
        allowed={"driver","transmission","polarity","strength","evidence_ids"}
        if set(c)-allowed: raise ValueError("causal chain contains unknown fields")
        driver = str(c.get("driver","")).strip()
        transmission = str(c.get("transmission","")).strip()
        polarity = str(c.get("polarity","")).upper().strip()
        refs = [str(x) for x in c.get("evidence_ids",[])]
        if not driver or not transmission:
            raise ValueError("driver/transmission required")
        if polarity not in VALID_POLARITY:
            raise ValueError("invalid polarity")
        if any(x not in valid_ids for x in refs):
            raise ValueError("causal chain uses unknown evidence id")
        out.append({
            "driver":driver[:180],
            "transmission":transmission[:260],
            "polarity":polarity,
            "strength":max(0,min(100,float(c.get("strength",0)))),
            "evidence_ids":refs[:8],
        })
    return {"chains":out}

CONTRACT = r"""
Return exactly:
{
 "chains":[
   {
     "driver":"...",
     "transmission":"driver -> intermediate mechanism -> NQ",
     "polarity":"BULLISH_NQ|BEARISH_NQ|MIXED|UNKNOWN",
     "strength":0,
     "evidence_ids":["E0001"]
   }
 ]
}
"""
