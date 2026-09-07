from __future__ import annotations
from typing import Any, Dict
from .phase33_common import raw_snapshot, fnum, clamp

def cross_asset_impulse(snapshot: Any) -> Dict[str,Any]:
    raw=raw_snapshot(snapshot)
    aliases={"NQ":("nq_change_pct","nq_futures_change_pct"),"ES":("es_change_pct","es_futures_change_pct"),"SPX":("spx_change_pct","spy_change_pct"),"QQQ":("qqq_change_pct",)}
    vals={}
    lower={str(k).lower():v for k,v in raw.items()}
    for name,keys in aliases.items():
        val=None
        for k in keys:
            if k in lower and lower[k] not in (None,""): val=fnum(lower[k]); break
        vals[name]=val
    avail={k:v for k,v in vals.items() if v is not None}
    if len(avail)<2: return {"status":"MISSING_NOT_FAKED","changes_pct":vals,"lead_candidate":None,"score":None}
    # Relative impulse: equity proxies leading NQ in same direction strengthens evidence.
    peers=[v for k,v in avail.items() if k!="NQ"]
    peer=sum(peers)/len(peers) if peers else 0.0; nq=avail.get("NQ",0.0); div=peer-nq
    lead=max((k for k in avail if k!="NQ"),key=lambda k:abs(avail[k]),default=None)
    return {"status":"AVAILABLE","changes_pct":vals,"peer_mean":round(peer,4),"peer_minus_nq":round(div,4),"lead_candidate":lead,"score":round(clamp(peer/1.5,-1,1),4)}
