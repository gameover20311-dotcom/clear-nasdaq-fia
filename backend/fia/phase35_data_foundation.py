from __future__ import annotations
import csv, io, json, os, time, math
from bisect import bisect_right
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .artifact_guard import guarded_output_path  # A6 sealed-artifact guard

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "fia_phase35" / "data"
LIC_DIR = ROOT / "fia_phase35" / "licensed_inputs"
START = os.getenv("FIA_PHASE35_START", "2025-09-01")
END = os.getenv("FIA_PHASE35_END", "2026-09-01")

PUBLIC_SYMBOLS = {
    "VIX":"^VIX", "VXN":"^VXN", "QQQ":"QQQ", "SPY":"SPY", "SMH":"SMH", "SOX":"^SOX",
    "AAPL":"AAPL","MSFT":"MSFT","NVDA":"NVDA","AMZN":"AMZN","META":"META","AVGO":"AVGO",
    "TSLA":"TSLA","GOOGL":"GOOGL","NFLX":"NFLX","AMD":"AMD","MU":"MU","INTC":"INTC",
}
FRED_SERIES={"US2Y":"DGS2","US10Y":"DGS10","REAL_YIELD":"DFII10"}

def _dt(x:Any)->datetime:
    if isinstance(x,datetime): d=x
    else:
        s=str(x or "").strip().replace("Z","+00:00")
        d=datetime.fromisoformat(s)
    if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)

def _num(x, default=None):
    try:
        if x is None or x=="": return default
        v=float(x)
        if math.isnan(v) or math.isinf(v): return default
        return v
    except Exception:return default

def _write_json(path:Path,obj:Any):
    # A6: every JSON written by this module passes the sealed-artifact guard.
    path=guarded_output_path(path)
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(obj,indent=2,default=str),encoding='utf-8')

def _download_yfinance()->Dict[str,Any]:
    out={"provider":"yfinance","interval":"1h","symbols":{},"errors":{}}
    try: import yfinance as yf
    except Exception as e:
        out["fatal"]=f"yfinance import failed: {e}"; return out
    for key,sym in PUBLIC_SYMBOLS.items():
        try:
            h=yf.download(sym,start=START,end=END,interval='1h',auto_adjust=False,progress=False,threads=False)
            rows=[]
            if h is not None and len(h):
                # yfinance may return MultiIndex columns on newer versions.
                def col(name):
                    c=h[name]
                    try:
                        if getattr(c,'ndim',1)>1: c=c.iloc[:,0]
                    except Exception: pass
                    return c
                oc,hh,ll,cc,vv=col('Open'),col('High'),col('Low'),col('Close'),col('Volume')
                for i,idx in enumerate(h.index):
                    t=idx.to_pydatetime() if hasattr(idx,'to_pydatetime') else _dt(idx)
                    if t.tzinfo is None: t=t.replace(tzinfo=timezone.utc)
                    else: t=t.astimezone(timezone.utc)
                    # Yahoo intraday index is bar start. Store completed bar end to enforce PTI.
                    end=t+timedelta(hours=1)
                    c=_num(cc.iloc[i]);
                    if c is None: continue
                    rows.append({"bar_start":t.isoformat(),"bar_end":end.isoformat(),"open":_num(oc.iloc[i]),"high":_num(hh.iloc[i]),"low":_num(ll.iloc[i]),"close":c,"volume":_num(vv.iloc[i],0.0)})
            out['symbols'][key]={"ticker":sym,"rows":rows,"n":len(rows)}
        except Exception as e: out['errors'][key]=repr(e)
    return out

def _download_fred()->Dict[str,Any]:
    out={"provider":"FRED","series":{},"errors":{}}
    try: import requests
    except Exception as e: out['fatal']=f"requests import failed: {e}"; return out
    for key,series in FRED_SERIES.items():
        try:
            u=f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={START}&coed={END}"
            r=requests.get(u,timeout=20); r.raise_for_status(); rows=[]
            for row in csv.DictReader(io.StringIO(r.text)):
                v=_num(row.get(series)); d=row.get('DATE') or row.get('observation_date')
                if v is None or not d: continue
                rows.append({"date":d,"value":v})
            out['series'][key]={"series_id":series,"rows":rows,"n":len(rows)}
        except Exception as e: out['errors'][key]=repr(e)
    return out

def _load_existing_futures()->Dict[str,Any]:
    candidates={
      'NQ': ROOT/'fia_backtest_phase20/data/nq_5m_multicontract_20250901_20260831.json',
      'ES': ROOT/'fia_backtest_phase28/data/es_5m_multicontract_20250901_20260831.json',
    }
    out={"provider":"existing_massive_futures","symbols":{},"errors":{}}
    for key,p in candidates.items():
        try:
            x=json.loads(p.read_text(encoding='utf-8')); rows=[]
            for b in x.get('bars') or []:
                t=_dt(b.get('timestamp')); c=_num(b.get('close'))
                if c is None: continue
                rows.append({"bar_end":(t+timedelta(minutes=5)).isoformat(),"close":c,"volume":_num(b.get('volume'),0.0),"contract":b.get('contract') or b.get('ticker')})
            out['symbols'][key]={"path":str(p),"rows":rows,"n":len(rows)}
        except Exception as e: out['errors'][key]=repr(e)
    return out

def _licensed_manifest()->Dict[str,Any]:
    """Detect genuine licensed exports. Never manufactures missing institutional data.
    Accepted CSV files (all optional): l2_l3.csv, options_gamma.csv, etf_flow.csv, volume_delta.csv.
    Every file must contain timestamp and its own numeric fields. Point-in-time as-of joins happen later.
    """
    names=['l2_l3.csv','options_gamma.csv','etf_flow.csv','volume_delta.csv']
    out={}
    for n in names:
        p=LIC_DIR/n
        if not p.exists(): out[n]={"status":"MISSING_NOT_FAKED","rows":0}; continue
        try:
            rows=list(csv.DictReader(p.open(encoding='utf-8')))
            valid=sum(1 for r in rows if r.get('timestamp'))
            out[n]={"status":"AVAILABLE","rows":valid,"path":str(p)}
        except Exception as e: out[n]={"status":"ERROR","error":repr(e),"rows":0}
    return out

def backfill(force:bool=False)->Dict[str,Any]:
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    yp=DATA_DIR/'public_hourly.json'; fp=DATA_DIR/'fred_daily.json'; futp=DATA_DIR/'existing_futures.json'
    if force or not yp.exists(): _write_json(yp,_download_yfinance())
    if force or not fp.exists(): _write_json(fp,_download_fred())
    if force or not futp.exists(): _write_json(futp,_load_existing_futures())
    result={"ok":True,"phase":"PHASE35 DATA BACKFILL","start":START,"end":END,
            "public_hourly":str(yp),"fred_daily":str(fp),"existing_futures":str(futp),
            "licensed":_licensed_manifest(),"missing_is_never_zero_or_neutral":True,
            "note":"Public data is fetched on the user's machine. Licensed-only feeds remain explicit MISSING_NOT_FAKED unless genuine timestamped exports are supplied."}
    _write_json(DATA_DIR/'backfill_manifest.json',result); return result

class TimeSeries:
    def __init__(self, rows:List[Dict[str,Any]], time_key='bar_end', value_key='close', max_age_minutes:Optional[int]=None):
        pts=[]
        for r in rows:
            try:
                t=_dt(r.get(time_key)); v=_num(r.get(value_key))
                if v is not None: pts.append((t,v,r))
            except Exception: pass
        pts.sort(key=lambda x:x[0]); self.pts=pts; self.times=[x[0] for x in pts]
        self.max_age_minutes=max_age_minutes
    def asof(self,t:datetime):
        i=bisect_right(self.times,t)-1
        if i<0: return None
        pt=self.pts[i]
        if self.max_age_minutes is not None:
            age=(t-pt[0]).total_seconds()/60.0
            if age < -1e-9 or age > float(self.max_age_minutes): return None
        return pt
    def ret(self,t:datetime,hours:int=1):
        a=self.asof(t); b=self.asof(t-timedelta(hours=hours))
        if not a or not b or not b[1]: return None
        return a[1]/b[1]-1.0

class DailySeries:
    def __init__(self,rows):
        pts=[]
        for r in rows:
            try: pts.append((datetime.fromisoformat(r['date']).date(),float(r['value'])))
            except Exception: pass
        pts.sort(); self.pts=pts; self.dates=[x[0] for x in pts]
    def prior(self,t:datetime):
        # Strict PTI: same-date end-of-day Treasury/FRED observation is not used intraday.
        target=t.date()-timedelta(days=1); i=bisect_right(self.dates,target)-1
        return self.pts[i][1] if i>=0 else None
    def change(self,t:datetime):
        target=t.date()-timedelta(days=1); i=bisect_right(self.dates,target)-1
        if i<1:return None
        return self.pts[i][1]-self.pts[i-1][1]

def load_store()->Dict[str,Any]:
    y=json.loads((DATA_DIR/'public_hourly.json').read_text()) if (DATA_DIR/'public_hourly.json').exists() else {"symbols":{}}
    fr=json.loads((DATA_DIR/'fred_daily.json').read_text()) if (DATA_DIR/'fred_daily.json').exists() else {"series":{}}
    fu=json.loads((DATA_DIR/'existing_futures.json').read_text()) if (DATA_DIR/'existing_futures.json').exists() else {"symbols":{}}
    # Fail closed on stale bars. Hourly Yahoo bars may be up to 90 minutes old
    # at an arbitrary checkpoint; 5m futures bars may be up to 15 minutes old.
    # Older observations are MISSING, never converted into a fake flat return.
    hourly={k:TimeSeries(v.get('rows') or [],max_age_minutes=90) for k,v in (y.get('symbols') or {}).items()}
    futures={k:TimeSeries(v.get('rows') or [],max_age_minutes=15) for k,v in (fu.get('symbols') or {}).items()}
    daily={k:DailySeries(v.get('rows') or []) for k,v in (fr.get('series') or {}).items()}
    return {"hourly":hourly,"futures":futures,"daily":daily,"raw":{"yfinance":y,"fred":fr,"futures":fu}}
