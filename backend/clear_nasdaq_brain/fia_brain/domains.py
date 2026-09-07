from __future__ import annotations
import re
from typing import Any, Dict, List, Set

# V6.6.1: markers are matched as normalized lexical tokens/phrases, never raw substrings.
# This prevents META<-metadata, MU<-cumulative and ISM<-transmission_mechanism contamination.
DOMAIN_MARKERS = {
    "macro_rates": (
        "macro","fed","fomc","cpi","pce","nfp","ism","gdp","dxy","us10y","tnx",
        "yield","inflation","jobs","employment","treasury","fred","financial conditions"
    ),
    "tech_leadership": (
        "nvda","msft","aapl","amzn","meta","avgo","goog","googl","tsla","amd","mu","intc",
        "semiconductor","semis","mega cap","breadth","leadership"
    ),
    "market_structure": (
        "price action","bar state","nq structure","spx confirmation","continuity",
        "above prior high","below prior low","prior high","prior low"
    ),
    "market_liquidity": (
        "liquidity","session","asia","london","new york","pdh","pdl","pwh","pwl",
        "sweep","swept","volume","orderflow","order flow","imbalance"
    ),
    "volatility": (
        "vix","volatility","implied volatility","options vol","options volatility"
    ),
    "catalyst_freshness": (
        "news","earnings","catalyst","calendar","release","sec","provider health","freshness",
        "stale sources","missing sources","checked at","upcoming","verified"
    ),
}

_SPLIT=re.compile(r"[^a-z0-9]+",re.I)

def _norm(x: Any) -> str:
    return " ".join(t for t in _SPLIT.split(str(x).lower()) if t)

def _hay(record: Dict[str, Any]) -> str:
    return _norm(" ".join([
        str(record.get("source","")),
        str(record.get("path","")),
        str(record.get("value",""))[:500],
    ]))

def _has_phrase(hay: str, marker: str) -> bool:
    m=_norm(marker)
    return bool(m) and (" "+m+" ") in (" "+hay+" ")

def record_domains(record: Dict[str, Any]) -> Set[str]:
    hay=_hay(record)
    out={name for name,markers in DOMAIN_MARKERS.items() if any(_has_phrase(hay,m) for m in markers)}
    return out or {"general"}

def partition(ledger: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out={k:[] for k in DOMAIN_MARKERS}; out["general"]=[]
    for r in ledger.get("records",[]):
        for d in record_domains(r):
            out.setdefault(d,[]).append(r)
    return out

def domain_text(ledger: Dict[str, Any],domain: str,max_records: int=72) -> str:
    parts=partition(ledger); rows=list(parts.get(domain,[]))
    if domain!="general":
        rows += list(parts.get("general",[]))[:12]
    seen=set(); lines=[]
    for r in rows:
        eid=str(r.get("evidence_id"))
        if eid in seen: continue
        seen.add(eid)
        v=r.get("value")
        if isinstance(v,str):
            v=" ".join(v.replace("\x00"," ").split())[:600]
        lines.append(f'{eid} | {r.get("source")} | {r.get("path")} = {json_safe(v)}')
        if len(lines)>=max_records: break
    return "\n".join(lines)

def json_safe(v: Any) -> str:
    import json
    return json.dumps(v,ensure_ascii=False)
