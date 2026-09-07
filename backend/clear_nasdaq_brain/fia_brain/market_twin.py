from __future__ import annotations
import math,re
from typing import Any, Dict, List
from .util import sha256_obj

_WORD=re.compile(r"[a-z0-9]+",re.I)

def _key(x: str) -> str:
    toks=_WORD.findall(str(x).lower())[:8]
    return "_".join(toks)[:96] or "unknown"

def build(causal_graph: Dict[str,Any]) -> Dict[str,Any]:
    """Deterministic market twin derived from the validated causal graph.
    It does not invent edges; it compresses causal commitments and exposes conflict/concentration.
    """
    agg={}
    for c in causal_graph.get('chains',[]):
        k=_key(c.get('driver',''))
        a=agg.setdefault(k,{'driver':str(c.get('driver',''))[:180],'bull':0.0,'bear':0.0,'mixed':0.0,'unknown':0.0,'evidence_ids':set(),'chains':0})
        s=max(0.0,min(100.0,float(c.get('strength',0))))
        pol=str(c.get('polarity','UNKNOWN')).upper()
        if pol=='BULLISH_NQ': a['bull']+=s
        elif pol=='BEARISH_NQ': a['bear']+=s
        elif pol=='MIXED': a['mixed']+=s
        else: a['unknown']+=s
        a['evidence_ids'].update(map(str,c.get('evidence_ids',[])))
        a['chains']+=1
    nodes=set(['NQ']); edges=[]
    for c in causal_graph.get('chains',[]):
        driver=str(c.get('driver','')).strip() or 'UNKNOWN'
        path=[x.strip() for x in str(c.get('transmission','')).split('->') if x.strip()]
        if not path: path=[driver,'NQ']
        elif len(path)==1: path=[driver,path[0],'NQ']
        else:
            if _key(path[0])!=_key(driver): path=[driver]+path
            if _key(path[-1]) not in {'nq','nasdaq','nasdaq_100'}: path.append('NQ')
        for a0,b0 in zip(path,path[1:]):
            nodes.add(a0); nodes.add(b0)
            edges.append({'from':a0[:140],'to':b0[:140],'polarity':str(c.get('polarity','UNKNOWN')).upper(),
                          'strength':round(max(0.0,min(100.0,float(c.get('strength',0)))),2),
                          'evidence_ids':[str(x) for x in c.get('evidence_ids',[])[:8]]})
    drivers=[]
    for k,a in agg.items():
        signed=a['bull']-a['bear']
        total=a['bull']+a['bear']+a['mixed']+a['unknown']
        conflict=min(a['bull'],a['bear'])/max(1.0,max(a['bull'],a['bear'])) if a['bull'] and a['bear'] else 0.0
        drivers.append({'driver_key':k,'driver':a['driver'],'signed_pressure':round(signed,2),'total_strength':round(total,2),
                        'conflict_ratio':round(conflict,4),'chains':a['chains'],'evidence_ids':sorted(a['evidence_ids'])[:12]})
    drivers.sort(key=lambda x:(-x['total_strength'],x['driver_key']))
    strengths=[x['total_strength'] for x in drivers if x['total_strength']>0]
    tot=sum(strengths)
    hhi=sum((x/tot)**2 for x in strengths) if tot else 0.0
    contradiction=max([x['conflict_ratio'] for x in drivers] or [0.0])
    bull=sum(max(0.0,x['signed_pressure']) for x in drivers)
    bear=sum(max(0.0,-x['signed_pressure']) for x in drivers)
    out={'drivers':drivers[:16],'driver_count':len(drivers),'bull_pressure':round(bull,2),'bear_pressure':round(bear,2),
         'concentration_hhi':round(hhi,4),'max_contradiction':round(contradiction,4),
         'dominant_driver_keys':[x['driver_key'] for x in drivers[:3]],'nodes':sorted(nodes)[:48],'edges':edges[:48]}
    out['market_twin_sha256']=sha256_obj(out)
    return out

def confidence_cap(twin: Dict[str,Any]) -> float:
    cap=100.0
    if float(twin.get('max_contradiction',0))>=0.75: cap=min(cap,45.0)
    elif float(twin.get('max_contradiction',0))>=0.45: cap=min(cap,60.0)
    if float(twin.get('concentration_hhi',0))>=0.70: cap=min(cap,55.0)
    return cap
