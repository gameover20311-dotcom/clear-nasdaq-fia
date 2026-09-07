from __future__ import annotations
from typing import Any, Dict
from .phase34_common import raw_snapshot, f

def black_swan(snapshot:Any)->Dict[str,Any]:
    raw=raw_snapshot(snapshot); move=abs(f(raw.get('nq_1m_return_pct'))); vix_jump=abs(f(raw.get('vix_5m_change_pct'))); spread=f(raw.get('spread_multiple'),1.0); news=str(raw.get('breaking_risk','')).upper()
    trig=move>=1.5 or vix_jump>=8 or spread>=4 or news in {'EXTREME','HALT','FLASH_CRASH'}
    return {'triggered':trig,'research_action':'FREEZE_NEW_ALERTS_AND_REQUIRE_HUMAN_REVIEW' if trig else 'NORMAL','automatic_close_or_hedge':False,'broker_execution':False,'inputs':{'nq_1m_return_pct':move,'vix_5m_change_pct':vix_jump,'spread_multiple':spread,'breaking_risk':news}}
def prop_guard(snapshot:Any)->Dict[str,Any]:
    raw=raw_snapshot(snapshot); daily=f(raw.get('daily_pnl_pct')); overall=f(raw.get('overall_drawdown_pct')); dlim=raw.get('prop_daily_loss_limit_pct'); olim=raw.get('prop_overall_loss_limit_pct')
    breach=(dlim is not None and daily<=-abs(f(dlim))) or (olim is not None and overall>=abs(f(olim)))
    return {'breach':bool(breach),'status':'BLOCK_RESEARCH_ALERT_ESCALATION' if breach else 'OK_OR_NOT_CONFIGURED','automatic_orders':False,'daily_pnl_pct':daily,'overall_drawdown_pct':overall,'limits':{'daily':dlim,'overall':olim}}
