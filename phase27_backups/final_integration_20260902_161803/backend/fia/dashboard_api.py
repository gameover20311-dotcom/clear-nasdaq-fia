import csv
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fia.liquidity import build_liquidity_map

TRACKED={"NVDA","MSFT","AAPL","AMZN","META","AVGO","GOOGL","GOOG","TSLA","NFLX","AMD","MU","INTC","QCOM","SMCI"}
CANDIDATES=[Path('fia_backtest_phase21/results/phase21_no_neutral_backtest_1y.csv'),Path('fia_backtest_phase20/results/phase20_full_backtest_1y.csv')]

def truthy(v): return str(v or '').strip().lower() in {'1','true','yes','y'}
def num(v):
    try: return float(v)
    except: return None

def ser(v):
    if is_dataclass(v): return asdict(v)
    if hasattr(v,'model_dump'): return v.model_dump()
    if hasattr(v,'dict'): return v.dict()
    if hasattr(v,'__dict__'): return v.__dict__
    return v

def accuracy(rows,h):
    ak=f'actual_{h}'; ck=f'correct_{h}'
    r=[x for x in rows if str(x.get(ak) or '').strip()]
    c=sum(1 for x in r if truthy(x.get(ck)))
    return {'resolved':len(r),'correct':c,'accuracy':round(100*c/len(r),2) if r else None}

def conf(rows,h):
    ak=f'actual_{h}'; out=[]
    for lo,hi in [(0,50),(50,60),(60,70),(70,101)]:
        s=[x for x in rows if str(x.get(ak) or '').strip() and num(x.get('confidence')) is not None and lo<=num(x.get('confidence'))<hi]
        c=sum(1 for x in s if str(x.get('predicted') or '').upper()==str(x.get(ak) or '').upper())
        out.append({'band':f'{lo}-{hi}%','n':len(s),'accuracy':round(100*c/len(s),2) if s else None})
    return out

def brier(rows,h):
    ak=f'actual_{h}'; vals=[]
    for x in rows:
        a=str(x.get(ak) or '').upper(); p=num(x.get('bullish_probability'))
        if a not in {'BULLISH','BEARISH'} or p is None: continue
        y=1.0 if a=='BULLISH' else 0.0
        vals.append((p/100-y)**2)
    return {'n':len(vals),'brier':round(sum(vals)/len(vals),4) if vals else None}

def monthly(rows):
    g=defaultdict(list)
    for x in rows:
        ts=str(x.get('timestamp') or '')
        if len(ts)>=7: g[ts[:7]].append(x)
    out=[]
    for m in sorted(g):
        a4=accuracy(g[m],'4h'); a8=accuracy(g[m],'8h')
        out.append({'month':m,'forecasts':len(g[m]),'accuracy_4h':a4['accuracy'],'resolved_4h':a4['resolved'],'accuracy_8h':a8['accuracy'],'resolved_8h':a8['resolved']})
    return out

def earnings_compare(rows):
    e=[x for x in rows if truthy(x.get('earnings_catalyst_risk'))]
    o=[x for x in rows if not truthy(x.get('earnings_catalyst_risk'))]
    return {'earnings_catalyst_days':{'days':len(e),'4h':accuracy(e,'4h'),'8h':accuracy(e,'8h')},'other_days':{'days':len(o),'4h':accuracy(o,'4h'),'8h':accuracy(o,'8h')}}

def load_backtest():
    p=next((x for x in CANDIDATES if x.exists()),None)
    if not p: return {'available':False,'reason':'Backtest CSV not found'}
    with p.open(newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
    return {
        'available':True,'phase':'PHASE 21 NO-NEUTRAL','file':str(p),'forecasts':len(rows),
        'accuracy_4h':accuracy(rows,'4h'),'accuracy_8h':accuracy(rows,'8h'),
        'predictions':dict(Counter(str(x.get('predicted') or 'UNKNOWN').upper() for x in rows)),
        'confidence_4h':conf(rows,'4h'),'confidence_8h':conf(rows,'8h'),
        'brier_4h':brier(rows,'4h'),'brier_8h':brier(rows,'8h'),
        'monthly':monthly(rows),'earnings_comparison':earnings_compare(rows),
        'data_quality':{
            'future_eps_used':sum(1 for x in rows if truthy(x.get('earnings_future_eps_used'))),
            'liquidity_resolutions':dict(Counter(str(x.get('liquidity_resolution') or 'missing') for x in rows)),
            'liquidity_contracts':dict(Counter(str(x.get('liquidity_contract') or 'missing') for x in rows)),
            'news_evidence':dict(Counter(str(x.get('news_evidence') or 'missing') for x in rows)),
            'earnings_evidence':dict(Counter(str(x.get('earnings_evidence') or 'missing') for x in rows)),
        },
    }

async def upcoming(hub):
    key=getattr(hub,'keys',{}).get('FINNHUB_API_KEY')
    if not key: return {'available':False,'events':[]}
    start=datetime.now(timezone.utc).date(); end=start+timedelta(days=7)
    r=await hub.get('https://finnhub.io/api/v1/calendar/earnings',{'from':start.isoformat(),'to':end.isoformat(),'token':key},timeout=15)
    events=[]
    for e in (r or {}).get('earningsCalendar',[]):
        s=str(e.get('symbol') or '').upper()
        if s in TRACKED:
            events.append({'symbol':s,'date':e.get('date'),'hour':e.get('hour'),'eps_estimate':e.get('epsEstimate'),'revenue_estimate':e.get('revenueEstimate')})
    events.sort(key=lambda e:(str(e.get('date') or ''),str(e.get('hour') or ''),e['symbol']))
    return {'available':True,'events':events}

async def build_dashboard_payload(hub, build_forecast):
    snapshot = await hub.snapshot()
    if isinstance(snapshot, dict) and isinstance(snapshot.get('data'), dict):
        data = snapshot['data']
        forecast_input = snapshot
    elif isinstance(snapshot, dict):
        data = snapshot
        forecast_input = {'data': data}
    else:
        data = {}
        forecast_input = {'data': {}}
    forecast = build_forecast(forecast_input)
    levels = build_liquidity_map(data)
    return {'ok':True,'generated_at':datetime.now(timezone.utc).isoformat(),'live':{'snapshot':snapshot,'forecast':ser(forecast),'liquidity':{k:ser(v) for k,v in levels.items()},'upcoming_earnings':await upcoming(hub)},'backtest':load_backtest()}
