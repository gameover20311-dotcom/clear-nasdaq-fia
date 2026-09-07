from __future__ import annotations
from typing import Any,Dict,List,Set
from .util import sha256_obj

POL={'BULLISH_NQ','BEARISH_NQ','MIXED','UNKNOWN'}

def validate(obj: Any, valid_ids: Set[str]) -> Dict[str,Any]:
    if not isinstance(obj,dict) or not isinstance(obj.get('hypotheses'),list): raise ValueError('hypotheses object/list required')
    if set(obj)!={'hypotheses'}: raise ValueError('hypotheses contains unknown top-level fields')
    out=[]; seen=set()
    for raw in obj['hypotheses'][:8]:
        if not isinstance(raw,dict): raise ValueError('hypothesis must be object')
        allowed={'hypothesis_id','claim','polarity','confidence','evidence_for','evidence_against','activation_conditions','invalidation_conditions'}
        if set(raw)-allowed: raise ValueError('hypothesis contains unknown fields')
        hid=str(raw.get('hypothesis_id','')).strip().upper()
        if not hid or hid in seen: raise ValueError('unique hypothesis_id required')
        seen.add(hid)
        claim=str(raw.get('claim','')).strip(); pol=str(raw.get('polarity','UNKNOWN')).upper()
        ef=[str(x) for x in raw.get('evidence_for',[])]; ea=[str(x) for x in raw.get('evidence_against',[])]
        if not claim or pol not in POL: raise ValueError('invalid hypothesis')
        if any(x not in valid_ids for x in ef+ea): raise ValueError('unknown evidence id in hypothesis')
        if set(ef)&set(ea): raise ValueError('same evidence cannot be both for and against one hypothesis')
        out.append({'hypothesis_id':hid[:24],'claim':claim[:280],'polarity':pol,
                    'confidence':round(max(0,min(100,float(raw.get('confidence',0)))),2),
                    'evidence_for':ef[:10],'evidence_against':ea[:10],
                    'activation_conditions':[str(x)[:220] for x in raw.get('activation_conditions',[])[:5]],
                    'invalidation_conditions':[str(x)[:220] for x in raw.get('invalidation_conditions',[])[:5]]})
    if len(out)<2: raise ValueError('at least two competing hypotheses required')
    result={'hypotheses':out}; result['hypothesis_ledger_sha256']=sha256_obj(result); return result

def pressure(book: Dict[str,Any]) -> Dict[str,Any]:
    bull=bear=0.0
    for h in book.get('hypotheses',[]):
        c=float(h.get('confidence',0))
        if h.get('polarity')=='BULLISH_NQ': bull+=c
        elif h.get('polarity')=='BEARISH_NQ': bear+=c
    total=bull+bear
    signed=(bull-bear)/max(1.0,total)
    conflict=min(bull,bear)/max(1.0,max(bull,bear)) if bull and bear else 0.0
    return {'bull_mass':round(bull,2),'bear_mass':round(bear,2),'signed_pressure':round(signed,4),'conflict_ratio':round(conflict,4)}

CONTRACT=r'''
Return exactly:
{"hypotheses":[
 {"hypothesis_id":"H1","claim":"...","polarity":"BULLISH_NQ|BEARISH_NQ|MIXED|UNKNOWN","confidence":0,
  "evidence_for":["E0001"],"evidence_against":["E0002"],
  "activation_conditions":["..."],"invalidation_conditions":["..."]}
]}
Create competing hypotheses, not paraphrases of one thesis.
'''
