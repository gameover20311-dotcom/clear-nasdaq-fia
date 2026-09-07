from __future__ import annotations
import os, time, csv, io
from typing import Any, Dict
from .phase34_common import utcnow, f
_CACHE:Dict[str,Any]={'at':0.0,'data':{}}

def _yf(symbols):
    try:
        import yfinance as yf
        out={}
        for key,sym in symbols.items():
            h=yf.Ticker(sym).history(period='5d',interval='5m',auto_adjust=False)
            if h is None or len(h)<1: continue
            last=float(h['Close'].iloc[-1]); prev=float(h['Close'].iloc[-2]) if len(h)>1 else last
            out[key]={'value':last,'change_pct':0.0 if prev==0 else (last/prev-1)*100,'source':f'yfinance:{sym}','as_of':str(h.index[-1])}
        return out
    except Exception: return {}

def _fred_csv(series:str):
    try:
        import requests
        url=f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}'
        r=requests.get(url,timeout=4); r.raise_for_status(); rows=list(csv.DictReader(io.StringIO(r.text)))
        vals=[]
        for row in rows[-20:]:
            try: vals.append(float(row[series]))
            except Exception: pass
        if not vals: return None
        return {'value':vals[-1],'change':(vals[-1]-vals[-2]) if len(vals)>1 else 0.0,'source':f'FRED:{series}','as_of':rows[-1].get('DATE') or rows[-1].get('observation_date')}
    except Exception: return None

def collect_public_inputs(force:bool=False)->Dict[str,Any]:
    # Network is opt-in so production cannot silently introduce latency or an unversioned source.
    enabled=os.getenv('FIA_PHASE34_PUBLIC_NETWORK','0').lower() in {'1','true','yes','on'}
    if not enabled: return {'ok':True,'status':'NETWORK_OPT_IN_DISABLED','data':{},'enable_with':'FIA_PHASE34_PUBLIC_NETWORK=1'}
    ttl=max(30,int(os.getenv('FIA_PHASE34_PUBLIC_TTL_SECONDS','120')))
    now=time.time()
    if not force and now-_CACHE['at']<ttl: return {'ok':True,'status':'CACHE','data':_CACHE['data']}
    data=_yf({'VIX':'^VIX','VXN':'^VXN','SMH':'SMH','QQQ':'QQQ','SPY':'SPY','SOX':'^SOX'})
    for key,series in [('US2Y','DGS2'),('US10Y','DGS10'),('REAL_YIELD','DFII10')]:
        x=_fred_csv(series)
        if x: data[key]=x
    _CACHE.update(at=now,data=data)
    return {'ok':True,'status':'LIVE_FETCH','data':data,'fetched_at':utcnow()}
