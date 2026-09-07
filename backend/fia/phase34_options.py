from __future__ import annotations
from typing import Any, Dict
from .phase34_common import raw_snapshot, f, clamp, missing

def analyze_options(snapshot:Any)->Dict[str,Any]:
    raw=raw_snapshot(snapshot); rows=raw.get('options_chain') or raw.get('qqq_options_chain')
    if not isinstance(rows,list) or not rows: return missing('OPTIONS_SURFACE','requires_timestamped_options_chain')
    puts=[]; calls=[]; gex=0.0; expiries=set()
    spot=f(raw.get('qqq_price',raw.get('spot',0.0)))
    for r in rows:
        if not isinstance(r,dict): continue
        iv=f(r.get('iv',r.get('implied_volatility')),float('nan')); gamma=f(r.get('gamma')); oi=max(0.0,f(r.get('open_interest',r.get('oi')))); strike=f(r.get('strike')); typ=str(r.get('type',r.get('right',''))).upper()
        if iv==iv and iv>0:
            (puts if typ.startswith('P') else calls).append((strike,iv))
        if gamma and oi and spot>0: gex += gamma*oi*100*spot*spot*(1 if typ.startswith('C') else -1)
        if r.get('expiry'): expiries.add(str(r.get('expiry')))
    piv=sum(iv for _,iv in puts)/len(puts) if puts else None; civ=sum(iv for _,iv in calls)/len(calls) if calls else None
    skew=(piv-civ) if piv is not None and civ is not None else None
    # Positive gex is treated as pinning/mean-reverting context; negative as destabilizing context, not directional alpha.
    gamma_regime='POSITIVE_GAMMA_PINNING' if gex>0 else 'NEGATIVE_GAMMA_ACCELERATION' if gex<0 else 'FLAT_OR_UNKNOWN'
    return {'status':'AVAILABLE','put_iv_mean':piv,'call_iv_mean':civ,'skew':skew,'dealer_gamma_proxy':gex,'gamma_regime':gamma_regime,'expiries':len(expiries),'directional_score':None,'note':'Options inputs affect regime/reliability unless OOS evidence approves directional use.'}
