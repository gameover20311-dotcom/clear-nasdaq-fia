from __future__ import annotations
from typing import Any, Dict, List
from .phase34_common import raw_snapshot, f, clamp, missing

def _levels(rows:Any,limit=25):
    out=[]
    for r in list(rows or [])[:limit]:
        if isinstance(r,dict): p=f(r.get('price')); q=f(r.get('size',r.get('qty',r.get('quantity'))))
        elif isinstance(r,(list,tuple)) and len(r)>=2: p,q=f(r[0]),f(r[1])
        else: continue
        if p>0 and q>=0: out.append((p,q))
    return out

def analyze_depth(snapshot:Any)->Dict[str,Any]:
    raw=raw_snapshot(snapshot); book=raw.get('order_book') or raw.get('l2') or raw.get('market_depth')
    if not isinstance(book,dict): return missing('L2_L3','requires_verified_depth_feed')
    bids=_levels(book.get('bids')); asks=_levels(book.get('asks'))
    if not bids or not asks: return missing('L2_L3','empty_depth_book')
    bq=sum(q for _,q in bids); aq=sum(q for _,q in asks); den=bq+aq
    imb=(bq-aq)/den if den else 0.0
    bb,ba=bids[0][0],asks[0][0]; spread=max(0.0,ba-bb); mid=(ba+bb)/2.0
    micro=(ba*bids[0][1]+bb*asks[0][1])/(bids[0][1]+asks[0][1]) if bids[0][1]+asks[0][1]>0 else mid
    micro_bias=0 if spread<=0 else clamp((micro-mid)/(spread/2.0))
    events=raw.get('l3_events') or []
    adds=cancels=market=0.0
    for e in events[-2000:] if isinstance(events,list) else []:
        if not isinstance(e,dict): continue
        q=f(e.get('size',e.get('qty',1.0)),1.0); typ=str(e.get('type','')).upper()
        if 'CANCEL' in typ: cancels+=q
        elif 'ADD' in typ or 'NEW' in typ: adds+=q
        elif 'TRADE' in typ or 'EXEC' in typ: market+=q
    cancel_ratio=cancels/max(1e-9,adds+cancels)
    spoof_risk='ELEVATED' if (adds+cancels)>0 and cancel_ratio>0.80 and market<0.15*(adds+cancels) else 'LOW_OR_UNPROVEN'
    score=clamp(.65*imb+.35*micro_bias)
    return {'status':'AVAILABLE','score':round(score,4),'depth_imbalance':round(imb,4),'microprice_bias':round(micro_bias,4),'spread':spread,'mid':mid,'bid_depth':bq,'ask_depth':aq,'l3_cancel_ratio':round(cancel_ratio,4) if adds+cancels else None,'spoof_risk':spoof_risk,'source':'snapshot_verified_depth'}
