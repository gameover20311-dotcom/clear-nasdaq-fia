from __future__ import annotations
import json,math,statistics
from pathlib import Path
from typing import Any,Dict,List,Optional
FEATURE_NAMES=('domain_macro_rates','domain_tech_leadership','domain_market_structure','domain_market_liquidity','domain_volatility','domain_catalyst_freshness','domain_general',
               'fresh_fresh','fresh_aging','fresh_stale','fresh_unknown','numeric_ratio','nullish_ratio','independence_ratio')

def fit(genomes: List[Dict[str,Any]], min_n: int=30) -> Dict[str,Any]:
    if len(genomes)<min_n: raise ValueError('need at least %d TRAIN genomes'%min_n)
    stats={}
    for k in FEATURE_NAMES:
        vals=[float((g.get('vector') or {}).get(k,0)) for g in genomes]
        med=statistics.median(vals); mad=statistics.median([abs(x-med) for x in vals])
        stats[k]={'median':round(med,8),'mad':round(max(mad,0.01),8)}
    return {'enabled':True,'training_split':'TRAIN','n':len(genomes),'features':stats}

def load(path: str) -> Optional[Dict[str,Any]]:
    p=Path(path)
    if not p.exists(): return None
    def bad(x): raise ValueError('non-finite regime profile: '+x)
    obj=json.loads(p.read_text(encoding='utf-8'),parse_constant=bad)
    if not isinstance(obj,dict) or not obj.get('enabled'): return None
    if obj.get('training_split')!='TRAIN' or int(obj.get('n',0))<30: return None
    for k,s in (obj.get('features') or {}).items():
        med=float(s.get('median')); mad=float(s.get('mad'))
        if not math.isfinite(med) or not math.isfinite(mad) or mad<=0: raise ValueError('invalid regime profile numeric')
    return obj

def score(genome: Dict[str,Any], profile: Optional[Dict[str,Any]]) -> Dict[str,Any]:
    if not profile: return {'enabled':False,'novelty_score':0.0,'confidence_cap':100.0,'top_deviations':[]}
    vec=genome.get('vector') or {}; dev=[]
    for k,s in (profile.get('features') or {}).items():
        z=abs(float(vec.get(k,0))-float(s['median']))/max(0.01,float(s['mad'])*1.4826)
        dev.append((z,k))
    dev.sort(reverse=True); top=dev[:4]; score0=sum(min(z,8.0) for z,_ in top)/max(1,len(top))
    # robust novelty is intentionally conservative; it caps confidence, never creates direction.
    cap=100.0
    if score0>=5: cap=40.0
    elif score0>=3.5: cap=55.0
    elif score0>=2.5: cap=70.0
    return {'enabled':True,'novelty_score':round(score0,3),'confidence_cap':cap,
            'top_deviations':[{'feature':k,'robust_z':round(z,3)} for z,k in top]}
