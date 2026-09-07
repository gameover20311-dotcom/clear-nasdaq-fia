from __future__ import annotations
import random, math
from typing import Any, Dict, List
from .phase34_common import f, clamp

def fractional_kelly_research(p:float, win_loss_ratio:float=2.0, fraction:float=.25)->Dict[str,Any]:
    p=clamp(p,0,1); b=max(1e-9,win_loss_ratio); q=1-p; full=(b*p-q)/b; frac=max(0.0,full)*max(0,min(1,fraction))
    return {'full_kelly':round(full,4),'fractional_kelly':round(frac,4),'execution_allowed':False,'research_only':True}
def monte_carlo_research(p:float,rr:float=2.0,trades:int=100,paths:int=500)->Dict[str,Any]:
    p=clamp(p,0,1); ends=[]; worst=[]
    rng=random.Random(34)
    for _ in range(paths):
        eq=0.0; peak=0.0; dd=0.0
        for _ in range(trades):
            eq += rr if rng.random()<p else -1.0; peak=max(peak,eq); dd=min(dd,eq-peak)
        ends.append(eq); worst.append(dd)
    ends.sort(); worst.sort()
    return {'paths':paths,'median_r_units':ends[len(ends)//2],'p05_r_units':ends[int(.05*len(ends))],'median_max_drawdown_r':worst[len(worst)//2],'research_only':True}
def sor_simulation(quotes:List[Dict[str,Any]],side='BUY',qty=1.0)->Dict[str,Any]:
    valid=[q for q in quotes if isinstance(q,dict) and f(q.get('ask' if side.upper()=='BUY' else 'bid'))>0]
    valid.sort(key=lambda q:f(q.get('ask')) if side.upper()=='BUY' else -f(q.get('bid')))
    return {'status':'SIMULATION_ONLY','side':side.upper(),'qty':qty,'ranked_venues':valid[:8],'orders_sent':False,'broker_execution':False}
