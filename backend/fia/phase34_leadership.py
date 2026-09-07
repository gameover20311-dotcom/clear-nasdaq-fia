from __future__ import annotations
from typing import Any, Dict
from .phase34_common import raw_snapshot, f, clamp
# Approximate NDX weights are intentionally NOT hard-coded: current weights drift and must be supplied/versioned.
def analyze_leadership(snapshot:Any, fallback_mega=None, fallback_semi=None)->Dict[str,Any]:
    raw=raw_snapshot(snapshot); comps=raw.get('index_components') or raw.get('mega_cap_components')
    contrib=[]
    if isinstance(comps,list):
        for r in comps:
            if not isinstance(r,dict): continue
            w=f(r.get('weight')); ret=f(r.get('return_pct',r.get('change_pct')))
            if w>0: contrib.append((str(r.get('symbol','?')),w,ret,w*ret))
    if contrib:
        tot=sum(w for _,w,_,_ in contrib); score=clamp(sum(c for *_,c in contrib)/max(1e-9,tot)/2.0)
        top=sorted(contrib,key=lambda x:abs(x[3]),reverse=True)[:8]
        mega={'status':'AVAILABLE','score':round(score,4),'top_contributors':[{'symbol':s,'weight':w,'return_pct':r,'impact':c} for s,w,r,c in top],'weight_source':'snapshot_versioned'}
    else: mega={'status':'FALLBACK_EXISTING_FIA_SIGNAL' if fallback_mega is not None else 'MISSING_NOT_FAKED','score':fallback_mega}
    semi_rows=raw.get('semiconductor_components')
    if isinstance(semi_rows,list) and semi_rows:
        rets=[f(r.get('return_pct',r.get('change_pct'))) for r in semi_rows if isinstance(r,dict)]
        pos=sum(x>0 for x in rets); breadth=(pos/len(rets)*2-1) if rets else 0.0
        semi={'status':'AVAILABLE','score':round(clamp(breadth),4),'advancers':pos,'total':len(rets)}
    else: semi={'status':'FALLBACK_EXISTING_FIA_SIGNAL' if fallback_semi is not None else 'MISSING_NOT_FAKED','score':fallback_semi}
    return {'mega_cap_index_impact':mega,'semiconductor_breadth':semi}
