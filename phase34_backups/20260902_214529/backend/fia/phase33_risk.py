from __future__ import annotations
import math, random
from typing import Any, Dict
from .phase33_common import fnum, raw_snapshot, clamp


def black_swan_guard(snapshot: Any, institutional: Dict[str,Any], news: Dict[str,Any]) -> Dict[str,Any]:
    raw=raw_snapshot(snapshot); nqchg=abs(fnum(raw.get("nq_change_pct",raw.get("nq_futures_change_pct"))))
    vix=(institutional.get("inputs") or {}).get("VIX",{}); vixchg=abs(fnum(vix.get("change_pct")))
    extreme_news=(news.get("events") and len(news.get("events",[]))>=3 and (news.get("primary_source_articles") or 0)>=1)
    triggered=nqchg>=2.0 or vixchg>=12.0 or bool(raw.get("flash_crash_flag"))
    return {"triggered":triggered,"action":"HALT_NEW_RESEARCH_ALERTS" if triggered else "NORMAL","automatic_close_or_hedge":False,"reason":{"nq_abs_change_pct":nqchg,"vix_abs_change_pct":vixchg,"extreme_news_context":bool(extreme_news)}}


def prop_guardrail(snapshot: Any) -> Dict[str,Any]:
    raw=raw_snapshot(snapshot); daily=fnum(raw.get("prop_daily_drawdown_pct")); overall=fnum(raw.get("prop_overall_drawdown_pct")); limits=raw.get("prop_limits") or {}
    dlim=fnum(limits.get("daily_drawdown_pct"),0); olim=fnum(limits.get("overall_drawdown_pct"),0)
    breach=(dlim>0 and daily>=dlim) or (olim>0 and overall>=olim)
    return {"status":"AVAILABLE" if limits else "NOT_CONFIGURED","breach":breach,"action":"BLOCK_RESEARCH_ENTRY_CANDIDATE" if breach else "NONE","broker_enforcement":False}


def monte_carlo_risk_diagnostic(probability: float, reward_to_risk: float=1.0, trials:int=2000) -> Dict[str,Any]:
    p=clamp(probability,0.001,0.999); b=max(0.01,reward_to_risk); k=max(0.0,min(1.0,(b*p-(1-p))/b))
    rng=random.Random(33); outcomes=[]
    for _ in range(trials): outcomes.append(b if rng.random()<p else -1.0)
    mean=sum(outcomes)/len(outcomes); var=sum((x-mean)**2 for x in outcomes)/len(outcomes)
    return {"simulation_only":True,"theoretical_kelly_fraction":round(k,4),"expected_R":round(mean,4),"std_R":round(math.sqrt(var),4),"not_applied_to_live_orders":True}
