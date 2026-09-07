from __future__ import annotations
import hashlib, re
from typing import Any, Dict, List
from urllib.parse import urlparse
from .phase33_common import raw_snapshot, fnum, clamp

PRIMARY_DOMAINS={"sec.gov","federalreserve.gov","bls.gov","bea.gov","treasury.gov","investor.nvidia.com","investor.apple.com","microsoft.com"}
EVENT_WORDS={"FOMC":["fomc","federal reserve","powell"],"CPI":["cpi","inflation"],"NFP":["payroll","jobs report","nfp"],"EARNINGS":["earnings","guidance","revenue","eps"],"REGULATION":["antitrust","regulation","sec ","doj"],"PRODUCT_AI":["ai","chip","gpu","product","launch"]}

def _domain(url:str)->str:
    try: return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception: return ""
def _norm(t:str)->str: return re.sub(r"[^a-z0-9 ]+"," ",t.lower()).strip()

def analyze_news(snapshot: Any) -> Dict[str,Any]:
    raw=raw_snapshot(snapshot); arts=raw.get("news_articles") or raw.get("news") or raw.get("articles") or []
    if not isinstance(arts,list): arts=[]
    seen=set(); rows=[]
    for a in arts[:80]:
        if not isinstance(a,dict): continue
        title=str(a.get("title") or a.get("headline") or ""); body=str(a.get("summary") or a.get("body") or "")
        text=(title+" "+body).strip(); url=str(a.get("url") or a.get("link") or "")
        key=hashlib.sha1(_norm(title)[:180].encode()).hexdigest() if title else hashlib.sha1(url.encode()).hexdigest()
        if key in seen: continue
        seen.add(key); dom=_domain(url); lower=text.lower(); events=[k for k,ws in EVENT_WORDS.items() if any(w in lower for w in ws)]
        primary=any(dom==d or dom.endswith("."+d) for d in PRIMARY_DOMAINS)
        surprise=a.get("surprise_score",a.get("surprise")); sentiment=a.get("sentiment_score",a.get("sentiment"))
        rows.append({"headline":title[:240],"url":url,"domain":dom,"primary_source":primary,"events":events,"sentiment":sentiment,"surprise":surprise})
    prim=sum(r["primary_source"] for r in rows); dup=max(0,len(arts)-len(rows))
    scored=[fnum(r.get("sentiment")) for r in rows if r.get("sentiment") not in (None,"")]
    sent=sum(scored)/len(scored) if scored else None
    return {"status":"AVAILABLE" if rows else "MISSING_NOT_FAKED","articles":len(rows),"duplicates_suppressed":dup,"primary_source_articles":prim,"primary_source_ratio":round(prim/len(rows),3) if rows else None,"sentiment_score":round(sent,4) if sent is not None else None,"events":sorted({e for r in rows for e in r["events"]}),"sample":rows[:8],"llm":{"status":"HOOK_AVAILABLE_DISABLED_BY_DEFAULT","env":"FIA_PHASE33_LLM"}}
