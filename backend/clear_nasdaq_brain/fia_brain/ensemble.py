from __future__ import annotations
import statistics
from collections import Counter
from typing import Any, Dict, List, Set, Optional

def _families(eids, valid_ids:Set[str], cluster_of:Optional[Dict[str,str]]) -> Set[str]:
    ids={str(e) for e in eids if str(e) in valid_ids}
    if not cluster_of:return ids
    return {str(cluster_of.get(e,e)) for e in ids}

def _candidate_weight(x: Dict[str, Any], valid_ids: Set[str], cluster_of: Optional[Dict[str,str]]=None) -> float:
    ref_families=_families(x.get("evidence_ids",[]),valid_ids,cluster_of)
    counter_families=_families(x.get("counter_evidence_ids",[]),valid_ids,cluster_of)
    unknowns=len(x.get("unknowns",[]))
    failures=len(x.get("failure_conditions",[]))
    confidence=max(0.0,min(100.0,float(x.get("confidence",50))))
    # Weight independent evidence families, never the number of correlated scalar fields.
    # Uncertainty must NEVER increase a candidate's voting power. Candidate confidence
    # is evidence-reliability metadata, so it influences weight only mildly.
    w=1.0
    w+=min(len(ref_families),8)*0.08
    w+=min(len(counter_families),5)*0.03
    w*=0.85+0.30*(confidence/100.0)
    w-=min(unknowns,5)*0.05
    w-=min(failures,4)*0.03
    return max(0.5,min(w,2.2))

def _top_refs(candidates: List[Dict[str, Any]], key: str, limit: int = 8) -> List[str]:
    c=Counter()
    for x in candidates:
        for eid in set(map(str,x.get(key,[]))): c[eid]+=1
    return [eid for eid,_ in c.most_common(limit)]

def aggregate(candidates: List[Dict[str, Any]], valid_ids: Set[str], cluster_of: Optional[Dict[str,str]]=None) -> Dict[str, Any]:
    if not candidates: raise ValueError("no candidates")
    ps=[];cs=[];ws=[]
    for x in candidates:
        p=float(x["bullish_probability"]); c=float(x["confidence"]); w=_candidate_weight(x,valid_ids,cluster_of)
        ps.append(p);cs.append(c);ws.append(w)
    total_w=sum(ws); mean_p=sum(p*w for p,w in zip(ps,ws))/total_w; mean_c=sum(c*w for c,w in zip(cs,ws))/total_w
    spread=statistics.pstdev(ps) if len(ps)>1 else 0.0; pmin,pmax=min(ps),max(ps)
    confidence_cap=max(15.0,100.0-2.2*spread); consensus_conf=min(mean_c,confidence_cap)
    direction_votes=Counter(str(x.get("direction","")) for x in candidates)
    bull_vote=direction_votes.get("BULLISH",0); bear_vote=direction_votes.get("BEARISH",0)
    if spread>=20 or (bull_vote and bear_vote and abs(bull_vote-bear_vote)<=1):
        direction="NO_EDGE" if consensus_conf<62 else ("BULLISH" if mean_p>=56 else ("BEARISH" if mean_p<=44 else "NEUTRAL"))
    else: direction="BULLISH" if mean_p>=56 else ("BEARISH" if mean_p<=44 else "NEUTRAL")
    return {"direction":direction,"bullish_probability":round(mean_p,2),"bearish_probability":round(100.0-mean_p,2),"confidence":round(consensus_conf,2),"candidate_count":len(candidates),"probability_spread_std":round(spread,2),"probability_range":[round(pmin,2),round(pmax,2)],"direction_votes":dict(direction_votes),"evidence_ids":_top_refs(candidates,"evidence_ids",10),"counter_evidence_ids":_top_refs(candidates,"counter_evidence_ids",8),"high_disagreement":bool(spread>=20),"cluster_aware_weighting":bool(cluster_of)}

def divergence(final: Dict[str, Any], consensus: Dict[str, Any]) -> Dict[str, Any]:
    gap=abs(float(final["bullish_probability"])-float(consensus["bullish_probability"]))
    dc=final.get("direction") in {"BULLISH","BEARISH"} and consensus.get("direction") in {"BULLISH","BEARISH"} and final.get("direction")!=consensus.get("direction")
    return {"probability_gap":round(gap,2),"direction_conflict":dc}
