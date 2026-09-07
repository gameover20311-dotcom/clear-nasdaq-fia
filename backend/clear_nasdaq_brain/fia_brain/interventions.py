from __future__ import annotations
from typing import Any,Dict
from .util import sha256_obj

def analyze(twin: Dict[str,Any]) -> Dict[str,Any]:
    """Leave-one-driver-out interventions on the deterministic twin.
    This is not a claim of real-world causality; it measures fragility of the model's own causal representation.
    """
    drivers=list(twin.get('drivers',[]))
    base=sum(float(x.get('signed_pressure',0)) for x in drivers)
    rows=[]
    for x in drivers[:8]:
        removed=float(x.get('signed_pressure',0)); after=base-removed
        base_sign=0 if abs(base)<1e-9 else (1 if base>0 else -1)
        after_sign=0 if abs(after)<1e-9 else (1 if after>0 else -1)
        rows.append({'driver_key':x.get('driver_key'),'removed_signed_pressure':round(removed,2),
                     'pressure_after_removal':round(after,2),'sign_flip':base_sign!=0 and after_sign!=0 and base_sign!=after_sign,
                     'directional_collapse':base_sign!=0 and after_sign==0,
                     'evidence_ids':list(x.get('evidence_ids',[]))[:10]})
    rows.sort(key=lambda z:(not z['sign_flip'],-abs(z['removed_signed_pressure']),str(z['driver_key'])))
    flip=sum(1 for x in rows if x['sign_flip']); collapse=sum(1 for x in rows if x.get('directional_collapse'))
    out={'base_net_pressure':round(base,2),'interventions':rows,'sign_flip_count':flip,'directional_collapse_count':collapse,
         'fragile_to_single_driver':bool(flip or collapse)}
    out['intervention_sha256']=sha256_obj(out)
    return out

def confidence_cap(obj: Dict[str,Any]) -> float:
    if obj.get('fragile_to_single_driver'): return 55.0
    return 100.0
