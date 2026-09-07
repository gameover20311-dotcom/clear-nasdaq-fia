from __future__ import annotations
from typing import Any, Dict
from .phase33_engine import analyze_phase33
from .phase33_common import signal_map
from .phase34_common import raw_snapshot, f, clamp
from .phase34_source_registry import audit_sources
from .phase34_public_data import collect_public_inputs
from .phase34_orderflow import analyze_depth
from .phase34_options import analyze_options
from .phase34_rates_vol import analyze_rates_vol
from .phase34_leadership import analyze_leadership
from .phase34_regime import regime_brain
from .phase34_news_primary import analyze_primary_news
from .phase34_event_surprise import analyze_event_surprise
from .phase34_analogs import nearest
from .phase34_calibration import apply as apply_calibration
from .phase34_rl_lab import rl_research_status, make_env_contract
from .phase34_risk_execution import fractional_kelly_research, monte_carlo_research
from .phase34_shields import black_swan, prop_guard
from .premove_engine import _history_read, DEFAULT_HISTORY, snapshot_row
from pathlib import Path

def _enrich(snapshot:Any, public:Dict[str,Any])->Any:
    if not isinstance(snapshot,dict): return snapshot
    out=dict(snapshot); data=dict(out.get('data') or {})
    for k,v in (public.get('data') or {}).items():
        if k not in data: data[k]=v
        # map object values to aliases used by Phase33 collector
        if isinstance(v,dict) and v.get('value') is not None:
            data.setdefault(k.lower(),v)
    out['data']=data; return out

def analyze_phase34(forecast:Any,snapshot:Any,record:bool=True)->Dict[str,Any]:
    public=collect_public_inputs(False); enriched=_enrich(snapshot,public)
    p33=analyze_phase33(forecast,enriched,record=record)
    sources=audit_sources(enriched); depth=analyze_depth(enriched); options=analyze_options(enriched)
    inst=p33.get('institutional_inputs') or {}; rates=analyze_rates_vol(inst)
    sm=signal_map(forecast); mega=sm.get('Mega-cap leadership',{}).get('score'); semi=sm.get('Semiconductors',{}).get('score')
    leadership=analyze_leadership(enriched,mega,semi)
    hist=_history_read(Path(DEFAULT_HISTORY)); cur=snapshot_row(forecast,enriched)
    regime=regime_brain(hist,f(cur.get('leading_score')),f(cur.get('price_score')),options)
    news=analyze_primary_news(enriched); event=analyze_event_surprise(enriched)
    raw=raw_snapshot(enriched)
    state={'lead':cur.get('leading_score'),'price':cur.get('price_score'),'vix':raw.get('vix'),'vxn':raw.get('vxn'),'us2y':raw.get('us2y'),'us10y':raw.get('us10y'),'real_yield':raw.get('real_yield'),'mega':leadership['mega_cap_index_impact'].get('score'),'semi':leadership['semiconductor_breadth'].get('score'),'breadth':sm.get('Breadth',{}).get('score'),'news':sm.get('News',{}).get('score'),'options_skew':options.get('skew') if isinstance(options,dict) else None,'gamma':options.get('dealer_gamma_proxy') if isinstance(options,dict) else None}
    analog=nearest(state)
    experts=[]
    def add(name,score,weight):
        if score is None or abs(f(score))<.06:return
        experts.append((name,1 if f(score)>0 else -1,weight))
    add('phase33',1 if p33.get('direction')=='BULLISH' else -1 if p33.get('direction')=='BEARISH' else 0,.30)
    if depth.get('status')=='AVAILABLE': add('L2_L3',depth.get('score'),.12)
    add('MEGACAP',leadership['mega_cap_index_impact'].get('score'),.10); add('SEMIS',leadership['semiconductor_breadth'].get('score'),.08)
    add('EVENT_SURPRISE',event.get('nasdaq_directional_score'),.10)
    if analog.get('observed_bullish_4h') is not None: add('ANALOG',(analog['observed_bullish_4h']-.5)*2,.10)
    # Options/regime/rates are reliability/context by default, not directional votes without OOS proof.
    total=sum(w for _,_,w in experts); signed=sum(s*w for _,s,w in experts)/total if total else 0.0
    agreement=(sum(w for _,s,w in experts if s==(1 if signed>=0 else -1))/total) if total else 0.0
    coverage=sources.get('coverage',0.0); strength=clamp(.55*(f(p33.get('decision_strength_0_100'))/100)+.25*abs(signed)+.20*agreement-.10*max(0,.45-coverage),0,1)
    direction='BULLISH' if signed>.06 else 'BEARISH' if signed<-.06 else str(p33.get('direction') or 'NEUTRAL')
    cal=apply_calibration((strength if direction=='BULLISH' else -strength)*3.0)
    shield=black_swan(enriched); prop=prop_guard(enriched)
    no_edge=agreement<.55 or shield['triggered'] or prop['breach'] or p33.get('state')=='NO_EDGE'
    state_name='NO_EDGE' if no_edge else 'PHASE34_HIGH_ALIGNMENT' if strength>=.72 and agreement>=.72 else 'PHASE34_PREMOVE_THESIS' if strength>=.52 else 'PHASE34_EARLY_WARNING'
    alert=state_name in {'PHASE34_PREMOVE_THESIS','PHASE34_HIGH_ALIGNMENT'} and bool((p33.get('phase32',{}).get('persistence_hysteresis') or {}).get('hysteresis',{}).get('confirmed')) and not no_edge
    p_for_risk=(cal.get('probability') or 50)/100
    return {'ok':True,'module':'FIA PHASE34 ALL-POINTS PRE-MOVE','version':'34.0','research_only':True,'broker_execution':False,'direction':direction,'state':state_name,'decision_strength_0_100':round(strength*100,1),'calibrated_probability':cal,'phase33':p33,'source_coverage':sources,'public_data_adapter':public,'l2_l3_orderflow':depth,'options_skew_gamma':options,'rates_volatility_brain':rates,'leadership_semis':leadership,'advanced_regime':regime,'primary_source_news':news,'event_surprise':event,'historical_analogs':analog,'rl_agent':{**rl_research_status(),'environment_contract':make_env_contract()},'risk_research':{'kelly':fractional_kelly_research(p_for_risk),'monte_carlo':monte_carlo_research(p_for_risk)},'shields':{'black_swan':shield,'prop_firm':prop},'ensemble':{'experts':[{'name':n,'vote':'BULLISH' if s>0 else 'BEARISH','weight':w} for n,s,w in experts],'signed_score':round(signed,4),'agreement':round(agreement,3),'active':len(experts),'context_only_until_oos':['OPTIONS','RATES_VOL','REGIME']},'alert':{'fire':bool(alert),'severity':'HIGH' if alert and state_name=='PHASE34_HIGH_ALIGNMENT' else 'MEDIUM' if alert else 'NONE','lead_time_status':'FORWARD_VALIDATION_REQUIRED'},'validation_gate':{'oos_required':True,'probability_90_95_not_forced':True,'missing_data_never_faked':True,'frozen_before_replay':True,'broker_execution_disabled':True}}
