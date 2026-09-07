from __future__ import annotations
from typing import Any, Dict, Iterable
from .phase33_common import raw_snapshot, signal_map, fnum, clamp, missing

ALIASES={
"US2Y":("us2y","us_2y","2y_yield","two_year_yield"),
"US10Y":("us10y","us_10y","10y_yield","ten_year_yield"),
"REAL_YIELD":("real_yield","real_yields","dfii10"),
"VIX":("vix","vix_price","vix_level"),"VXN":("vxn","vxn_price","vxn_level"),
"SOX":("sox","sox_price","semiconductor_index"),"SMH":("smh","smh_price"),
"OPTIONS_SKEW":("options_skew","qqq_skew","put_call_skew"),
"DEALER_GAMMA":("dealer_gamma","gex","gamma_exposure"),
"ETF_FLOW":("etf_flow","qqq_flow","etf_flows"),
"VOLUME_DELTA":("volume_delta","cvd","orderflow_delta"),
"FUTURES_BASIS":("futures_basis","nq_basis","nq_qqq_basis"),
}
SIGNAL_ALIASES={
"US10Y":("US10Y",),"SOX":("SOX","Semiconductors"),"SMH":("SMH confirmation",),
"VIX":("VIX",),"VXN":("VXN",),"REAL_YIELD":("Real yields","Real yield"),
"OPTIONS_SKEW":("Options skew","QQQ skew"),"DEALER_GAMMA":("Dealer gamma","GEX"),
"ETF_FLOW":("ETF flows","QQQ flows"),"VOLUME_DELTA":("Volume delta","CVD"),
"FUTURES_BASIS":("Futures basis","NQ basis")}


def _candidate(raw: Dict[str,Any], aliases: Iterable[str]):
    lower={str(k).lower():v for k,v in raw.items()}
    for a in aliases:
        if a.lower() in lower and lower[a.lower()] not in (None,""):
            return lower[a.lower()]
    return None


def collect_institutional_inputs(forecast: Any, snapshot: Any) -> Dict[str,Any]:
    raw=raw_snapshot(snapshot); sm=signal_map(forecast); out={}
    for name,aliases in ALIASES.items():
        val=_candidate(raw,aliases)
        if val is not None:
            if isinstance(val,dict):
                value=val.get("value",val.get("price",val.get("level")))
                change=val.get("change_pct",val.get("change"))
                score=val.get("score")
                out[name]={"status":"AVAILABLE","value":value,"change_pct":change,"score":score,"source":val.get("source","snapshot")}
            else:
                out[name]={"status":"AVAILABLE","value":val,"change_pct":None,"score":None,"source":"snapshot"}
            continue
        found=None
        for alias in SIGNAL_ALIASES.get(name,()):
            if alias in sm: found=sm[alias]; break
        if found:
            out[name]={"status":"AVAILABLE","value":None,"change_pct":None,"score":found["score"],"source":"fia_signal","freshness":found["freshness"]}
        else: out[name]=missing(name)
    # Rate-curve impulse is only computed when actual 2Y and 10Y levels exist.
    if out["US2Y"]["status"]=="AVAILABLE" and out["US10Y"]["status"]=="AVAILABLE":
        a=fnum(out["US2Y"].get("value"),float("nan")); b=fnum(out["US10Y"].get("value"),float("nan"))
        curve=None if a!=a or b!=b else b-a
        out["CURVE_2S10S"]={"status":"AVAILABLE" if curve is not None else "MISSING_NOT_FAKED","value":curve,"score":None}
    else: out["CURVE_2S10S"]=missing("CURVE_2S10S","requires_US2Y_and_US10Y_levels")
    available=sum(v.get("status")=="AVAILABLE" for v in out.values()); total=len(out)
    return {"inputs":out,"coverage":round(available/total,3) if total else 0.0,"available":available,"total":total}
