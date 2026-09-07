from __future__ import annotations
from typing import Any, Dict
from .phase33_common import raw_snapshot, fnum


def smart_order_routing_simulation(snapshot: Any) -> Dict[str,Any]:
    raw=raw_snapshot(snapshot); venues=raw.get("venue_quotes") or raw.get("broker_quotes") or []
    if not isinstance(venues,list) or not venues:
        return {"status":"NO_LIVE_EXECUTION","simulation":"MISSING_VENUE_QUOTES","route":[],"broker_calls":False}
    rows=[]
    for v in venues:
        if not isinstance(v,dict): continue
        rows.append({"venue":v.get("venue","unknown"),"bid":fnum(v.get("bid")),"ask":fnum(v.get("ask")),"size":fnum(v.get("size"))})
    rows.sort(key=lambda x:x["ask"] if x["ask"]>0 else 1e18)
    return {"status":"SIMULATION_ONLY","route":rows[:3],"broker_calls":False,"orders_created":False}
