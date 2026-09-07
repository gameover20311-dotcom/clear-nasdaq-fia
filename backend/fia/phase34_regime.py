from __future__ import annotations
import math, statistics
from typing import Any, Dict, List
from .phase33_regime import detect_advanced_regime
from .phase34_common import f, clamp

def _changepoint(vals:List[float]):
    if len(vals)<12: return {'detected':False,'z_like':0.0,'sample':len(vals)}
    a=vals[-12:-6]; b=vals[-6:]; ma=sum(a)/len(a); mb=sum(b)/len(b); sd=statistics.pstdev(vals[-12:])
    z=0.0 if sd<1e-9 else (mb-ma)/sd
    return {'detected':abs(z)>=1.25,'z_like':round(z,3),'direction':'UP' if z>0 else 'DOWN','sample':len(vals[-12:])}
def regime_brain(history:List[Dict[str,Any]], lead:float, price:float, options:Dict[str,Any]|None=None)->Dict[str,Any]:
    base=detect_advanced_regime(history,lead,price)
    vals=[f(r.get('leading_score')) for r in history[-32:]]+[lead]
    cp=_changepoint(vals)
    gamma=(options or {}).get('gamma_regime')
    risk='TRANSITION' if cp['detected'] else 'STABLE'
    if gamma=='NEGATIVE_GAMMA_ACCELERATION': risk='HIGH_CONVEXITY'
    return {'base':base,'change_point':cp,'transition_risk':risk,'options_gamma_regime':gamma,'dynamic_weight_policy':'REGIME_CAN_MODULATE_RELIABILITY_ONLY_UNTIL_OOS_APPROVAL'}
