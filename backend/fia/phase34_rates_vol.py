from __future__ import annotations
from typing import Any, Dict
from .phase34_common import f, clamp

def analyze_rates_vol(inputs:Dict[str,Any])->Dict[str,Any]:
    def val(k):
        x=(inputs.get('inputs') or inputs).get(k,{}) if isinstance(inputs,dict) else {}
        return x.get('value') if isinstance(x,dict) and x.get('status')=='AVAILABLE' else None
    us2,us10,real,vix,vxn=val('US2Y'),val('US10Y'),val('REAL_YIELD'),val('VIX'),val('VXN')
    curve=(f(us10)-f(us2)) if us2 is not None and us10 is not None else None
    available=sum(x is not None for x in [us2,us10,real,vix,vxn])
    # Levels alone do not create a directional impulse. Change/velocity belongs in time-series layer.
    return {'status':'AVAILABLE' if available else 'MISSING_NOT_FAKED','US2Y':us2,'US10Y':us10,'REAL_YIELD':real,'VIX':vix,'VXN':vxn,'curve_2s10s':curve,'available_components':available,'directional_score':None,'reason':'requires_timestamped_changes_for_directional_impulse'}
