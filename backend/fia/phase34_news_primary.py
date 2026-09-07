from __future__ import annotations
import re, hashlib
from typing import Any, Dict, List
from urllib.parse import urlparse
from .phase34_common import raw_snapshot, f
PRIMARY={'sec.gov':'SEC','federalreserve.gov':'FED','bls.gov':'BLS','bea.gov':'BEA','treasury.gov':'TREASURY'}
def _norm(t:str)->str: return re.sub(r'\W+',' ',(t or '').lower()).strip()
def analyze_primary_news(snapshot:Any)->Dict[str,Any]:
    raw=raw_snapshot(snapshot); arts=raw.get('articles') or raw.get('news_articles') or raw.get('news')
    if not isinstance(arts,list): return {'status':'MISSING_NOT_FAKED','articles':0,'clusters':0,'primary_verified':0}
    seen={}; rows=[]; primary=0
    for a in arts[-300:]:
        if not isinstance(a,dict): continue
        title=str(a.get('title',a.get('headline',''))); body=str(a.get('body',a.get('summary',''))); url=str(a.get('url',''))
        domain=urlparse(url).netloc.lower().replace('www.','')
        ptype=next((v for k,v in PRIMARY.items() if domain==k or domain.endswith('.'+k)),None)
        if ptype: primary+=1
        key=hashlib.sha1((_norm(title)+' '+_norm(body)[:300]).encode()).hexdigest()[:16]
        if key in seen: seen[key]['duplicates']+=1; continue
        row={'title':title[:240],'url':url,'domain':domain,'primary_source':ptype,'duplicates':0,'published_at':a.get('published_at',a.get('datetime')),'first_seen_at':a.get('first_seen_at'),'sentiment':a.get('sentiment'),'surprise':a.get('surprise'),'nasdaq_impact':a.get('nasdaq_impact')}
        seen[key]=row; rows.append(row)
    novelty=1.0-(sum(r['duplicates'] for r in rows)/max(1,len(arts)))
    return {'status':'AVAILABLE','articles':len(arts),'clusters':len(rows),'primary_verified':primary,'duplicate_suppression':True,'novelty_ratio':round(max(0.0,novelty),3),'top_clusters':rows[-20:]}
