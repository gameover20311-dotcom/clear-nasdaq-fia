from __future__ import annotations
import csv,json,math,re
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List
from .phase35_data_foundation import ROOT, DATA_DIR, LIC_DIR, _dt, _num, load_store

SRC=ROOT/'fia_backtest_phase29/results/phase29_outcome_revalidated_1y.csv'
NEWS=ROOT/'fia_backtest_phase20/data/polygon_news_20250901_20260831.json'
EARN=ROOT/'fia_backtest_phase20/data/earnings_events_sec_verified_20250901_20260831.json'
OUT=DATA_DIR/'enriched_pti.jsonl'
MEGA=['AAPL','MSFT','NVDA','AMZN','META','AVGO','TSLA','GOOGL','NFLX']
SEMIS=['NVDA','AVGO','AMD','MU','INTC']
IMPACT={'AAPL':1.0,'MSFT':1.0,'NVDA':1.0,'AMZN':.8,'META':.8,'AVGO':.7,'TSLA':.6,'GOOGL':.8,'NFLX':.3}

def _sent(x):
    x=str(x or '').lower()
    return 1 if x=='positive' else -1 if x=='negative' else 0

def _tokens(s): return set(re.findall(r'[a-z0-9]{3,}',str(s or '').lower()))
def _jacc(a,b):
    u=a|b
    return len(a&b)/len(u) if u else 0.0

def _load_news():
    try:x=json.loads(NEWS.read_text()); arr=x.get('articles') or []
    except Exception: arr=[]
    rows=[]
    for a in arr:
        try:t=_dt(a.get('published_utc'))
        except Exception:continue
        score=0.0; n=0
        for z in a.get('insights') or []:
            s=_sent(z.get('sentiment'))
            if s: score+=s; n+=1
        # An article with no scored sentiment is not a neutral sentiment vote.
        rows.append((t,a,score/n if n else None,_tokens((a.get('title') or '')+' '+(a.get('description') or ''))))
    rows.sort(key=lambda x:x[0]); return rows

def _load_earn():
    try:x=json.loads(EARN.read_text()); arr=x.get('events') or []
    except Exception: arr=[]
    rows=[]
    for e in arr:
        try:t=_dt(e.get('reveal_at'))
        except Exception:continue
        rows.append((t,e))
    rows.sort(key=lambda x:x[0]); return rows

def _news_features(news,news_times,t):
    i0=bisect_left(news_times,t-timedelta(hours=6)); i1=bisect_right(news_times,t)
    p0=bisect_left(news_times,t-timedelta(hours=30)); p1=bisect_left(news_times,t-timedelta(hours=6))
    recent=news[i0:i1]
    prev=news[p0:p1]
    if not recent:return {"news_count_6h":0,"news_scored_count_6h":0,"news_sentiment":None,"news_novelty":None,"news_primary_ratio":None}
    scored=[x[2] for x in recent if x[2] is not None]
    sent=(sum(scored)/len(scored)) if scored else None
    ptoken=[x[3] for x in prev[-300:]]; nov=[]
    for _,a,_,tok in recent:
        sim=max((_jacc(tok,q) for q in ptoken),default=0.0); nov.append(1-sim)
    official=0
    for _,a,_,_ in recent:
        u=str(a.get('article_url') or '').lower(); pub=str((a.get('publisher') or {}).get('name') or '').lower()
        if any(k in u for k in ['sec.gov','federalreserve.gov','bls.gov','bea.gov','treasury.gov']) or any(k in pub for k in ['sec','federal reserve','bureau of labor','treasury']): official+=1
    return {"news_count_6h":len(recent),"news_scored_count_6h":len(scored),"news_sentiment":round(sent,4) if sent is not None else None,"news_novelty":round(sum(nov)/len(nov),4),"news_primary_ratio":round(official/len(recent),4)}

def _earn_features(earn,earn_times,t):
    i0=bisect_left(earn_times,t-timedelta(hours=48)); i1=bisect_right(earn_times,t)
    recent=[e for _,e in earn[i0:i1]]
    if not recent:return {"earnings_surprise":None,"earnings_count_48h":0}
    vals=[]
    for e in recent:
        s=_num(e.get('surprise_percent'))
        if s is not None: vals.append(max(-1,min(1,s/25.0)))
    return {"earnings_surprise":round(sum(vals)/len(vals),4) if vals else None,"earnings_count_48h":len(recent)}

def _ret(ts,t,h=1): return ts.ret(t,h) if ts else None

def _group_return(hourly,names,t,h=1,weights=None):
    vals=[]
    for n in names:
        r=_ret(hourly.get(n),t,h)
        if r is not None: vals.append((r,(weights or {}).get(n,1.0)))
    den=sum(w for _,w in vals)
    return sum(v*w for v,w in vals)/den if den else None

def _market_features(store,t):
    h=store['hourly']; f=store['futures']; d=store['daily']
    q1=_ret(h.get('QQQ'),t,1); s1=_ret(h.get('SPY'),t,1); smh=_ret(h.get('SMH'),t,1); sox=_ret(h.get('SOX'),t,1)
    nq1=_ret(f.get('NQ'),t,1); es1=_ret(f.get('ES'),t,1)
    vix=_ret(h.get('VIX'),t,1); vxn=_ret(h.get('VXN'),t,1)
    mega=_group_return(h,MEGA,t,1,IMPACT); semi=_group_return(h,SEMIS,t,1)
    us2=d.get('US2Y').prior(t) if d.get('US2Y') else None; us2c=d.get('US2Y').change(t) if d.get('US2Y') else None
    us10=d.get('US10Y').prior(t) if d.get('US10Y') else None; us10c=d.get('US10Y').change(t) if d.get('US10Y') else None
    ry=d.get('REAL_YIELD').prior(t) if d.get('REAL_YIELD') else None; ryc=d.get('REAL_YIELD').change(t) if d.get('REAL_YIELD') else None
    # Cross-asset confirmation, using only completed bars. Positive means risk-on/NQ supportive.
    riskon=[x for x in [q1,s1,nq1,es1] if x is not None]
    cross=sum(riskon)/len(riskon) if riskon else None
    # Futures basis proxy: relative 1h impulse difference, NOT a fair-value basis and never mislabeled as one.
    basis_proxy=(nq1-q1) if nq1 is not None and q1 is not None else None
    return {"qqq_ret_1h":q1,"spy_ret_1h":s1,"nq_ret_1h":nq1,"es_ret_1h":es1,"smh_ret_1h":smh,"sox_ret_1h":sox,
            "mega_impact_ret_1h":mega,"semi_breadth_ret_1h":semi,"vix_ret_1h":vix,"vxn_ret_1h":vxn,
            "us2y_prior":us2,"us2y_change":us2c,"us10y_prior":us10,"us10y_change":us10c,"real_yield_prior":ry,"real_yield_change":ryc,
            "crossasset_riskon":cross,"futures_basis_proxy":basis_proxy}

def _load_licensed(name):
    p=LIC_DIR/name
    if not p.exists():return []
    try:
        rows=[]
        for r in csv.DictReader(p.open(encoding='utf-8')):
            if r.get('timestamp'): rows.append((_dt(r['timestamp']),r))
        rows.sort(key=lambda x:x[0]); return rows
    except Exception:return []

def _licensed_asof(rows,t,max_age_min=30):
    best=None
    for tt,r in rows:
        if tt<=t:best=(tt,r)
        else:break
    if not best or (t-best[0]).total_seconds()>max_age_min*60:return None
    out={}
    for k,v in best[1].items():
        if k=='timestamp':continue
        n=_num(v); out[k]=n if n is not None else v
    return out

def enrich()->Dict[str,Any]:
    if not SRC.exists(): raise RuntimeError(f'Missing {SRC}')
    store=load_store(); news=_load_news(); earn=_load_earn(); news_times=[x[0] for x in news]; earn_times=[x[0] for x in earn]
    licensed={n:_load_licensed(n) for n in ['l2_l3.csv','options_gamma.csv','etf_flow.csv','volume_delta.csv']}
    rows=list(csv.DictReader(SRC.open(encoding='utf-8'))); OUT.parent.mkdir(parents=True,exist_ok=True)
    enriched=[]; coverage=[]
    for r in rows:
        t=_dt(r['timestamp']); z={"timestamp":r['timestamp'],"base":r}
        z.update(_market_features(store,t)); z.update(_news_features(news,news_times,t)); z.update(_earn_features(earn,earn_times,t))
        z['licensed']={k:_licensed_asof(v,t) for k,v in licensed.items()}
        wanted=['vix_ret_1h','vxn_ret_1h','us2y_change','real_yield_change','mega_impact_ret_1h','semi_breadth_ret_1h','crossasset_riskon','news_sentiment','news_novelty','earnings_surprise','futures_basis_proxy']
        av=sum(z.get(k) is not None for k in wanted); z['historical_feature_coverage']=round(av/len(wanted),3); coverage.append(z['historical_feature_coverage']); enriched.append(z)
    with OUT.open('w',encoding='utf-8') as f:
        for z in enriched:f.write(json.dumps(z,separators=(',',':'),default=str)+'\n')
    result={"ok":True,"rows":len(enriched),"output":str(OUT),"mean_feature_coverage":round(sum(coverage)/len(coverage),3) if coverage else 0.0,
            "point_in_time_rules":["hourly bars require bar_end <= forecast timestamp","FRED/Treasury daily values use prior calendar date only","news published_at <= timestamp","earnings reveal_at <= timestamp","licensed feeds require timestamp <= checkpoint and max age"],
            "no_future_leakage_by_design":True,"missing_never_imputed_as_neutral":True}
    (DATA_DIR/'enrichment_summary.json').write_text(json.dumps(result,indent=2)); return result
