from __future__ import annotations
import json,math,csv
from collections import defaultdict
from pathlib import Path
from typing import Any,Dict,List,Tuple
from .phase35_data_foundation import ROOT,DATA_DIR,_num
from .artifact_guard import guarded_output_path  # A6 sealed-artifact guard

ENR=DATA_DIR/'enriched_pti.jsonl'
OUTDIR=ROOT/'fia_backtest_phase35/results'; OUTDIR.mkdir(parents=True,exist_ok=True)
POLICY=ROOT/'fia_phase35/PHASE35_FROZEN_POLICY.json'

def clamp(x,a=-1,b=1):return max(a,min(b,x))
def sig(x):return 1/(1+math.exp(-max(-30,min(30,x))))
def scale_ret(x,den): return None if x is None else clamp(x/den)
def scale_change(x,den): return None if x is None else clamp(x/den)
def _base_signal(r):
    b=r['base']; p=_num(b.get('bullish_probability')); return None if p is None else clamp((p-50)/35)

def feature_votes(r):
    # Frozen before replay. Only genuine available features enter; missing features do not become zero votes.
    vals=[]
    def add(name,x,w):
        if x is not None: vals.append((name,clamp(x),w))
    add('BASE_FIA',_base_signal(r),.22)
    add('CROSS_ASSET',scale_ret(r.get('crossasset_riskon'),.004),.12)
    add('MEGA_CAP',scale_ret(r.get('mega_impact_ret_1h'),.005),.10)
    add('SEMIS',scale_ret(r.get('semi_breadth_ret_1h'),.006),.08)
    # Rising volatility/rates/real yields are typically NQ headwinds, hence inverse signs.
    add('VIX',None if r.get('vix_ret_1h') is None else -scale_ret(r.get('vix_ret_1h'),.025),.07)
    add('VXN',None if r.get('vxn_ret_1h') is None else -scale_ret(r.get('vxn_ret_1h'),.025),.07)
    add('US2Y',None if r.get('us2y_change') is None else -scale_change(r.get('us2y_change'),.08),.06)
    add('US10Y',None if r.get('us10y_change') is None else -scale_change(r.get('us10y_change'),.08),.04)
    add('REAL_YIELD',None if r.get('real_yield_change') is None else -scale_change(r.get('real_yield_change'),.06),.05)
    add('NEWS',r.get('news_sentiment'),.06)
    # Novelty is reliability/amplitude. It cannot create direction by itself.
    ns=r.get('news_sentiment'); nv=r.get('news_novelty')
    if ns is not None and nv is not None:add('NEWS_NOVELTY',clamp(ns*nv),.03)
    add('EARNINGS_SURPRISE',r.get('earnings_surprise'),.05)
    add('FUTURES_BASIS_PROXY',scale_ret(r.get('futures_basis_proxy'),.003),.025)
    # Genuine licensed feeds, if present, use standardized field names only.
    lic=r.get('licensed') or {}
    l2=lic.get('l2_l3.csv') or {}; op=lic.get('options_gamma.csv') or {}; ef=lic.get('etf_flow.csv') or {}; vd=lic.get('volume_delta.csv') or {}
    add('L2_IMBALANCE',_num(l2.get('imbalance_score')),.04)
    add('DEALER_GAMMA',_num(op.get('gamma_directional_score')),.03)
    add('OPTIONS_SKEW',_num(op.get('skew_directional_score')),.025)
    add('ETF_FLOW',_num(ef.get('flow_directional_score')),.025)
    add('VOLUME_DELTA',_num(vd.get('delta_directional_score')),.025)
    return vals

def raw_score(r):
    v=feature_votes(r); den=sum(w for _,_,w in v)
    if not den:return 0.0,0.0,v
    z=sum(x*w for _,x,w in v)/den; cov=min(1.0,den/.9)
    # Fail-soft toward uncertainty, not toward bullish/bearish zero: score magnitude is shrunk when coverage is poor.
    return clamp(z*cov),cov,v

def fit_platt(xs,ys):
    a,b=1.0,0.0
    for _ in range(1600):
        ga=gb=0.0
        for x,y in zip(xs,ys):
            p=sig(a*x+b);e=p-y;ga+=e*x;gb+=e
        n=max(1,len(xs));a-=.04*ga/n;b-=.04*gb/n
    return a,b

def _truth(r,h):
    a=str(r['base'].get(f'actual_{h}') or '').upper(); return 1 if a=='BULLISH' else 0 if a=='BEARISH' else None

def _resolved(r,h):
    v=str(r['base'].get(f'correct_{h}') or '').lower(); return v in {'true','false','1','0','yes','no'}

def metrics(rows,h,pkey):
    resolved=[r for r in rows if _resolved(r,h) and r.get(pkey) is not None]
    if not resolved:return {'n':0}
    correct=0; binary=[]
    for r in resolved:
        p=r[pkey]; actual=str(r['base'].get(f'actual_{h}') or '').upper(); pred='BULLISH' if p>=.5 else 'BEARISH'; correct+=pred==actual
        y=_truth(r,h)
        if y is not None:binary.append((max(.001,min(.999,p)),y))
    ph=correct/len(resolved);z=1.96;den=1+z*z/len(resolved);center=(ph+z*z/(2*len(resolved)))/den;half=z*math.sqrt(ph*(1-ph)/len(resolved)+z*z/(4*len(resolved)**2))/den
    out={'n':len(resolved),'correct':correct,'incorrect':len(resolved)-correct,'accuracy':round(100*ph,2),'wilson95':[round(100*(center-half),2),round(100*(center+half),2)],'binary_probability_n':len(binary)}
    if binary:
        br=sum((p-y)**2 for p,y in binary)/len(binary);ll=-sum(y*math.log(p)+(1-y)*math.log(1-p) for p,y in binary)/len(binary);bins=defaultdict(list)
        for p,y in binary:bins[min(9,int(p*10))].append((p,y))
        ece=sum(len(a)/len(binary)*abs(sum(p for p,y in a)/len(a)-sum(y for p,y in a)/len(a)) for a in bins.values())
        out.update(brier=round(br,4),log_loss=round(ll,4),ece=round(ece,4))
    return out

def base_metrics(rows,h):
    rr=[r for r in rows if _resolved(r,h)];good=0;binary=[]
    for r in rr:
        b=r['base'];v=str(b.get(f'correct_{h}') or '').lower();good+=v in {'true','1','yes'}; y=_truth(r,h)
        p=_num(b.get('bullish_probability'))
        if y is not None and p is not None: binary.append((max(.001,min(.999,p/100)),y))
    return {'n':len(rr),'correct':good,'incorrect':len(rr)-good,'accuracy':round(100*good/len(rr),2) if rr else None,'brier':round(sum((p-y)**2 for p,y in binary)/len(binary),4) if binary else None}

def replay()->Dict[str,Any]:
    if not ENR.exists():raise RuntimeError(f'Missing {ENR}')
    rows=[json.loads(x) for x in ENR.read_text().splitlines() if x.strip()]
    for r in rows:
        z,c,v=raw_score(r);r['phase35_raw_score']=z;r['phase35_feature_coverage']=c;r['phase35_votes']=v
    cut=max(30,int(len(rows)*.70));dev=rows[:cut];hold=rows[cut:];models={}
    for h in ('4h','8h'):
        tr=[r for r in dev if _truth(r,h) is not None];xs=[r['phase35_raw_score']*3 for r in tr];ys=[_truth(r,h) for r in tr];a,b=fit_platt(xs,ys);models[h]=(a,b)
        for r in rows:r[f'phase35_p_{h}']=sig(a*r['phase35_raw_score']*3+b)
    devm={h:metrics(dev,h,f'phase35_p_{h}') for h in ('4h','8h')};holdm={h:metrics(hold,h,f'phase35_p_{h}') for h in ('4h','8h')};base={h:base_metrics(hold,h) for h in ('4h','8h')}
    approval=[]
    for h in ('4h','8h'):
        m,b=holdm[h],base[h]; approval.append(m.get('n',0)>=40 and ((m.get('accuracy',0)>=b.get('accuracy',0)+1.0) or (m.get('brier',9)<=b.get('brier',9)-.005)))
    approved=all(approval)
    cov=sum(r['phase35_feature_coverage'] for r in rows)/len(rows) if rows else 0
    licensed={k:any((r.get('licensed') or {}).get(k) for r in rows) for k in ['l2_l3.csv','options_gamma.csv','etf_flow.csv','volume_delta.csv']}
    result={'ok':True,'phase':'PHASE 35 ONE-SHOT INSTITUTIONAL DATA + FULL REPLAY','frozen_policy':True,'rows':len(rows),'development_rows':len(dev),'untouched_holdout_rows':len(hold),'mean_predictive_feature_coverage':round(cov,3),'dev':devm,'holdout':holdm,'base_holdout':base,'live_probability_approval':approved,'approval_rule':'Both 4H and 8H must improve untouched holdout by >=1pp accuracy OR >=0.005 Brier, with n>=40 each.','licensed_feed_presence':licensed,'rl_live_weight':0.0,'broker_execution':False,'fake_90_95_claim':False,'no_holdout_threshold_tuning':True,'missing_data_policy':'EXCLUDE_AND_SHRINK_STRENGTH_NOT_ZERO_IMPUTATION'}
    OUTDIR.mkdir(parents=True,exist_ok=True);guarded_output_path(OUTDIR/'phase35_full_replay_summary.json').write_text(json.dumps(result,indent=2));
    # Compact trace CSV for audit.
    with guarded_output_path(OUTDIR/'phase35_full_replay_trace.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['timestamp','raw_score','coverage','p4h','p8h','actual4h','actual8h'])
        for r in rows:w.writerow([r['timestamp'],round(r['phase35_raw_score'],6),round(r['phase35_feature_coverage'],4),round(r['phase35_p_4h'],6),round(r['phase35_p_8h'],6),r['base'].get('actual_4h'),r['base'].get('actual_8h')])
    return result
