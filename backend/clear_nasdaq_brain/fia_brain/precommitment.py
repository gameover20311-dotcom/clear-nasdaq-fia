from __future__ import annotations
from typing import Any,Dict
from .util import sha256_obj

def build(market_twin: Dict[str,Any], hypotheses: Dict[str,Any], scenarios: Dict[str,Any], interventions: Dict[str,Any]) -> Dict[str,Any]:
    h=[]
    for x in hypotheses.get('hypotheses',[]):
        h.append({'hypothesis_id':x['hypothesis_id'],'polarity':x['polarity'],'confidence':x['confidence'],
                  'evidence_for':x['evidence_for'],'evidence_against':x['evidence_against'],
                  'activation_conditions':x['activation_conditions'],'invalidation_conditions':x['invalidation_conditions']})
    out={'market_twin_sha256':market_twin.get('market_twin_sha256'),'intervention_sha256':interventions.get('intervention_sha256'),
         'hypotheses':h,'scenario_lattice_sha256':scenarios.get('scenario_lattice_sha256'),'scenario_worlds':scenarios.get('worlds',[])}
    out['precommitment_sha256']=sha256_obj(out); return out

def verify(obj: Dict[str,Any]) -> bool:
    if not isinstance(obj,dict): return False
    body={k:v for k,v in obj.items() if k!='precommitment_sha256'}
    return str(obj.get('precommitment_sha256'))==sha256_obj(body)
