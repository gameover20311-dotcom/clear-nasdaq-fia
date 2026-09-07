from __future__ import annotations
import os, time
from typing import Any, Dict
from .phase34_common import raw_snapshot, utcnow, sha, f

SOURCES={
 'VIX':{'snapshot':['vix','vix_level'],'env':'FIA_VIX_SOURCE','class':'PUBLIC_OR_VENDOR'},
 'VXN':{'snapshot':['vxn','vxn_level'],'env':'FIA_VXN_SOURCE','class':'PUBLIC_OR_VENDOR'},
 'US2Y':{'snapshot':['us2y','us_2y','two_year_yield'],'env':'FIA_US2Y_SOURCE','class':'OFFICIAL_FRED_OR_VENDOR'},
 'US10Y':{'snapshot':['us10y','us_10y','ten_year_yield'],'env':'FIA_US10Y_SOURCE','class':'OFFICIAL_FRED_OR_VENDOR'},
 'REAL_YIELD':{'snapshot':['real_yield','dfii10'],'env':'FIA_REAL_YIELD_SOURCE','class':'OFFICIAL_FRED_OR_VENDOR'},
 'SOX':{'snapshot':['sox','semiconductor_index'],'env':'FIA_SOX_SOURCE','class':'PUBLIC_OR_VENDOR'},
 'SMH':{'snapshot':['smh','smh_price'],'env':'FIA_SMH_SOURCE','class':'PUBLIC_OR_VENDOR'},
 'OPTIONS_SKEW':{'snapshot':['options_skew','qqq_skew'],'env':'FIA_OPTIONS_SOURCE','class':'OPTIONS_VENDOR'},
 'DEALER_GAMMA':{'snapshot':['dealer_gamma','gex'],'env':'FIA_GAMMA_SOURCE','class':'LICENSED_OR_DERIVED_OPTIONS'},
 'ETF_FLOW':{'snapshot':['etf_flow','qqq_flow'],'env':'FIA_ETF_FLOW_SOURCE','class':'VENDOR_OR_DERIVED'},
 'VOLUME_DELTA':{'snapshot':['volume_delta','cvd'],'env':'FIA_ORDERFLOW_SOURCE','class':'L2_L3_OR_TRADE_FEED'},
 'FUTURES_BASIS':{'snapshot':['futures_basis','nq_basis'],'env':'FIA_BASIS_SOURCE','class':'DERIVED_FROM_VERIFIED_MARKETS'},
 'L2_L3':{'snapshot':['order_book','l2','market_depth'],'env':'FIA_L2_SOURCE','class':'LICENSED_DEPTH'},
}

def _first(raw:Dict[str,Any], keys):
    low={str(k).lower():v for k,v in raw.items()}
    for k in keys:
        if k.lower() in low and low[k.lower()] not in (None,''): return low[k.lower()]
    return None

def audit_sources(snapshot:Any)->Dict[str,Any]:
    raw=raw_snapshot(snapshot); out={}
    for name,cfg in SOURCES.items():
        v=_first(raw,cfg['snapshot'])
        if v is None:
            out[name]={'status':'WAITING_FOR_REAL_SOURCE','source_class':cfg['class'],'configured':bool(os.getenv(cfg['env'])),'env':cfg['env'],'fake_imputation':False}
        else:
            out[name]={'status':'AVAILABLE','source_class':cfg['class'],'configured':True,'value':v,'first_seen_at':utcnow(),'checksum':sha(v),'fake_imputation':False}
    avail=sum(x['status']=='AVAILABLE' for x in out.values())
    return {'ok':True,'sources':out,'available':avail,'total':len(out),'coverage':round(avail/max(1,len(out)),3),'missing_never_neutral_imputed':True}
