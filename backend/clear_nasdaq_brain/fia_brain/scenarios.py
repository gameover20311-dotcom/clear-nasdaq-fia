from __future__ import annotations
import math
from typing import Any,Dict,Set
from .util import sha256_obj
KINDS={'BULL','BASE','BEAR'}

def validate(obj: Any, valid_ids: Set[str]) -> Dict[str,Any]:
    if not isinstance(obj,dict) or not isinstance(obj.get('worlds'),list): raise ValueError('worlds required')
    if set(obj)!={'worlds'}: raise ValueError('scenarios contains unknown top-level fields')
    worlds=[]; kinds=set()
    for raw in obj['worlds']:
        if not isinstance(raw,dict): raise ValueError('world must be object')
        allowed={'kind','probability','narrative','activation_conditions','break_conditions','evidence_ids'}
        if set(raw)-allowed: raise ValueError('scenario contains unknown fields')
        kind=str(raw.get('kind','')).upper(); prob=float(raw.get('probability',-1)); refs=[str(x) for x in raw.get('evidence_ids',[])]
        if kind not in KINDS or kind in kinds: raise ValueError('exact unique BULL/BASE/BEAR required')
        if not 0<=prob<=100 or any(x not in valid_ids for x in refs): raise ValueError('invalid scenario')
        kinds.add(kind); worlds.append({'kind':kind,'probability':round(prob,2),'narrative':str(raw.get('narrative',''))[:320],
            'activation_conditions':[str(x)[:220] for x in raw.get('activation_conditions',[])[:6]],
            'break_conditions':[str(x)[:220] for x in raw.get('break_conditions',[])[:6]],'evidence_ids':refs[:12]})
    if kinds!=KINDS: raise ValueError('must contain BULL BASE BEAR')
    if abs(sum(x['probability'] for x in worlds)-100)>0.6: raise ValueError('scenario probabilities must sum to 100')
    worlds.sort(key=lambda x:{'BULL':0,'BASE':1,'BEAR':2}[x['kind']])
    probs=[x['probability']/100 for x in worlds]
    entropy=-sum(p*math.log(p,3) for p in probs if p>0)
    result={'worlds':worlds,'entropy':round(entropy,4)}; result['scenario_lattice_sha256']=sha256_obj(result); return result

def confidence_cap(lattice: Dict[str,Any]) -> float:
    e=float(lattice.get('entropy',1))
    if e>=0.96:return 45.0
    if e>=0.90:return 55.0
    if e>=0.82:return 70.0
    return 100.0

CONTRACT=r'''
Return exactly three mutually exclusive worlds:
{"worlds":[
 {"kind":"BULL","probability":0,"narrative":"...","activation_conditions":["..."],"break_conditions":["..."],"evidence_ids":["E0001"]},
 {"kind":"BASE","probability":0,"narrative":"...","activation_conditions":["..."],"break_conditions":["..."],"evidence_ids":["E0002"]},
 {"kind":"BEAR","probability":0,"narrative":"...","activation_conditions":["..."],"break_conditions":["..."],"evidence_ids":["E0003"]}
]}
Probabilities must sum to 100. BASE means conflicted/range/no-edge path, not a disguised directional case.
'''
