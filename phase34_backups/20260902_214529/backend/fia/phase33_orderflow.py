from __future__ import annotations
from typing import Any, Dict, List
from .phase33_common import raw_snapshot, fnum, clamp


def analyze_orderflow(snapshot: Any) -> Dict[str,Any]:
    raw=raw_snapshot(snapshot)
    book=raw.get("order_book") or raw.get("l2") or raw.get("market_depth")
    cvd=raw.get("volume_delta",raw.get("cvd"))
    if not isinstance(book,dict) and cvd in (None,""):
        return {"status":"MISSING_NOT_FAKED","source_required":"licensed_or_verified_L2/L3_or_volume_delta","score":None,"imbalance":None,"spoof_risk":"UNKNOWN"}
    bids=(book or {}).get("bids",[]) if isinstance(book,dict) else []
    asks=(book or {}).get("asks",[]) if isinstance(book,dict) else []
    def qty(rows: List[Any]) -> float:
        s=0.0
        for r in rows[:20]:
            if isinstance(r,dict): s+=fnum(r.get("size",r.get("qty",r.get("quantity"))))
            elif isinstance(r,(list,tuple)) and len(r)>=2: s+=fnum(r[1])
        return s
    bq,aq=qty(bids),qty(asks); den=bq+aq
    imb=(bq-aq)/den if den>0 else 0.0
    cv=fnum(cvd,0.0)
    cv_score=clamp(cv/100000.0,-1,1) if cv not in (0.0,) else 0.0
    score=clamp(0.75*imb+0.25*cv_score,-1,1)
    # Spoof risk is intentionally conservative: without message-level add/cancel events, it stays UNKNOWN.
    return {"status":"AVAILABLE","score":round(score,4),"imbalance":round(imb,4),"bid_depth":round(bq,2),"ask_depth":round(aq,2),"volume_delta":cvd,"spoof_risk":"UNKNOWN_WITHOUT_L3_ADD_CANCEL_EVENTS"}
