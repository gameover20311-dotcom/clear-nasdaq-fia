from __future__ import annotations
from collections import Counter
from typing import Any,Dict
from .domains import record_domains
from .evidence_intelligence import freshness_hint,cluster_correlated
from .util import sha256_obj
FEATURES=('macro_rates','tech_leadership','market_structure','market_liquidity','volatility','catalyst_freshness','general')

def build(ledger: Dict[str,Any]) -> Dict[str,Any]:
    rec=list(ledger.get('records',[])); n=max(1,len(rec)); dom=Counter(); fresh=Counter(); numeric=0; nullish=0
    for x in rec:
        ds=record_domains(x)
        for d in ds: dom[d]+=1
        fresh[freshness_hint(x)]+=1
        v=x.get('value')
        if isinstance(v,(int,float)) and not isinstance(v,bool): numeric+=1
        if v is None or (isinstance(v,str) and v.strip().lower() in {'','none','null','missing','n/a','unknown'}): nullish+=1
    clusters=cluster_correlated(rec)
    vector={('domain_'+d):round(dom[d]/n,6) for d in FEATURES}
    for f in ('FRESH','AGING','STALE','UNKNOWN'): vector['fresh_'+f.lower()]=round(fresh[f]/n,6)
    vector['numeric_ratio']=round(numeric/n,6); vector['nullish_ratio']=round(nullish/n,6)
    vector['independence_ratio']=round(len(clusters)/n,6)
    record_content_sha256=sha256_obj([{'evidence_id':x.get('evidence_id'),'source':x.get('source'),'path':x.get('path'),'value':x.get('value'),'record_hash':x.get('record_hash')} for x in rec])
    out={'record_count':len(rec),'cluster_count':len(clusters),'vector':vector,'ledger_sha256':ledger.get('ledger_sha256'),'record_content_sha256':record_content_sha256}
    out['evidence_genome_sha256']=sha256_obj(out); return out
