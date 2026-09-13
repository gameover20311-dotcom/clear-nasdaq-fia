from __future__ import annotations
import csv,json,math,statistics,pathlib,sys
from collections import defaultdict
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia.phase33_common import fnum, clamp, sigmoid
from fia.artifact_guard import guarded_output_path
SRC=ROOT/"fia_backtest_phase29"/"results"/"phase29_outcome_revalidated_1y.csv"
OUTDIR=ROOT/"fia_backtest_phase33"/"results"; OUTDIR.mkdir(parents=True,exist_ok=True)
OUT=OUTDIR/"phase33_full_replay_1y.csv"; SUM=OUTDIR/"phase33_full_replay_1y_summary.json"; CAL=ROOT/"fia_phase33"/"data"/"phase33_calibration.json"
CORE=["NQ structure","SPX confirmation","DXY","US10Y","Mega-cap leadership","Semiconductors","Breadth","News","Macro calendar","Earnings/guidance"]

def signals(r):
    try: arr=json.loads(r.get("signals_json") or "[]")
    except Exception: arr=[]
    return {x.get("name"):fnum(x.get("score")) for x in arr if isinstance(x,dict)}
def sgn(x,d=.08): return 1 if x>d else -1 if x<-d else 0
def state_score(rows,i):
    r=rows[i]; s=signals(r); hist=rows[max(0,i-7):i+1]
    lead_names=["SPX confirmation","DXY","US10Y","Mega-cap leadership","Semiconductors","Breadth","News","Macro calendar","Earnings/guidance"]
    vals=[s.get(n) for n in lead_names if n in s and not (n in {"Macro calendar","Earnings/guidance"} and (r.get("macro_source_status") in {"unavailable_plan","missing"}))]
    lead=sum(vals)/len(vals) if vals else 0.0; price=s.get("NQ structure",0.0)
    aligned=[sgn(v) for v in vals if sgn(v)]; dom=1 if sum(x>0 for x in aligned)>=sum(x<0 for x in aligned) else -1
    align=(sum(x==dom for x in aligned)/len(aligned)) if aligned else .5
    prior_leads=[]
    for h in hist:
        hs=signals(h); hv=[hs.get(n) for n in lead_names if n in hs]; prior_leads.append(sum(hv)/len(hv) if hv else 0.0)
    persistence=(sum(sgn(x)==dom for x in prior_leads if sgn(x))/max(1,sum(bool(sgn(x)) for x in prior_leads)))
    accel=(prior_leads[-1]-prior_leads[0])/max(1,len(prior_leads)-1) if len(prior_leads)>1 else 0.0
    divergence=lead-price
    # Historical analog vote uses ONLY prior rows.
    analog=None
    if i>=12:
        cv=[(fnum(r.get("bullish_probability"))-50)/50,fnum(r.get("score")),lead,price,s.get("Mega-cap leadership",0),s.get("Semiconductors",0),s.get("Breadth",0)]
        cand=[]
        for j in range(i):
            rr=rows[j]; ss=signals(rr); vv=[(fnum(rr.get("bullish_probability"))-50)/50,fnum(rr.get("score")),sum(ss.get(n,0) for n in lead_names)/len(lead_names),ss.get("NQ structure",0),ss.get("Mega-cap leadership",0),ss.get("Semiconductors",0),ss.get("Breadth",0)]
            d=math.sqrt(sum((a-b)**2 for a,b in zip(cv,vv))/len(cv)); cand.append((d,rr))
        cand.sort(key=lambda x:x[0]); neigh=[x[1] for x in cand[:7]]; ys=[1 if x.get("actual_4h")=="BULLISH" else 0 for x in neigh if x.get("actual_4h") in {"BULLISH","BEARISH"}]
        analog=(sum(ys)/len(ys)-.5)*2 if ys else None
    components=[(lead,.30),(divergence,.14),((align*2-1)*dom,.16),((persistence*2-1)*dom,.12),(clamp(accel/.12,-1,1),.10),(fnum(r.get("score")),.10)]
    if analog is not None: components.append((analog,.08))
    den=sum(w for _,w in components); z=sum(clamp(v,-1,1)*w for v,w in components)/den
    return clamp(z,-1,1),lead,price,align,persistence,accel,analog

def fit_platt(xs,ys):
    a,b=1.0,0.0
    for _ in range(1200):
        ga=gb=0.0
        for x,y in zip(xs,ys):
            p=sigmoid(a*x+b); e=p-y; ga+=e*x; gb+=e
        n=max(1,len(xs)); a-=0.08*ga/n; b-=0.08*gb/n
    return a,b
def _resolved_bool(v):
    if isinstance(v,bool): return v
    t=str(v).strip().lower() if v is not None else ""
    if t in {"true","1","yes"}: return True
    if t in {"false","0","no"}: return False
    return None

def metrics(rows,pkey,h):
    # Accuracy uses the same strict resolved denominator as Phase29: neutral moves
    # are resolved losses for a binary BULLISH/BEARISH engine. Brier/log-loss/ECE
    # remain binary and therefore exclude NEUTRAL actuals, matching truth_metrics.py.
    resolved=[r for r in rows if _resolved_bool(r.get(f"correct_{h}")) is not None and r.get(pkey) is not None]
    if not resolved: return {"n":0}
    good=0
    binary=[]
    for r in resolved:
        p=clamp(float(r[pkey])/100,.001,.999); actual=str(r.get(f"actual_{h}") or "").upper(); pred="BULLISH" if p>=.5 else "BEARISH"
        good += pred==actual
        if actual in {"BULLISH","BEARISH"}: binary.append((p,1 if actual=="BULLISH" else 0))
    ph=good/len(resolved); z=1.96; den=1+z*z/len(resolved); center=(ph+z*z/(2*len(resolved)))/den; half=z*math.sqrt(ph*(1-ph)/len(resolved)+z*z/(4*len(resolved)**2))/den
    out={"n":len(resolved),"correct":good,"incorrect":len(resolved)-good,"accuracy":round(100*ph,2),"wilson95":[round(100*(center-half),2),round(100*(center+half),2)],"binary_probability_n":len(binary)}
    if binary:
        brier=sum((p-y)**2 for p,y in binary)/len(binary); ll=sum(-(y*math.log(p)+(1-y)*math.log(1-p)) for p,y in binary)/len(binary); bins=defaultdict(list)
        for p,y in binary: bins[int(p*10)].append((p,y))
        ece=sum(len(arr)/len(binary)*abs(sum(p for p,y in arr)/len(arr)-sum(y for p,y in arr)/len(arr)) for arr in bins.values())
        out.update({"brier":round(brier,4),"log_loss":round(ll,4),"ece":round(ece,4)})
    else: out.update({"brier":None,"log_loss":None,"ece":None})
    return out

def base_metrics(rows,h):
    resolved=[r for r in rows if _resolved_bool(r.get(f"correct_{h}")) is not None]
    if not resolved:return {"n":0}
    good=sum(_resolved_bool(r.get(f"correct_{h}")) is True for r in resolved)
    binary=[r for r in resolved if str(r.get(f"actual_{h}") or "").upper() in {"BULLISH","BEARISH"}]
    bs=None
    if binary:
        bs=sum(((fnum(r.get("bullish_probability"))/100)-(1 if r[f"actual_{h}"]=="BULLISH" else 0))**2 for r in binary)/len(binary)
    return {"n":len(resolved),"correct":good,"incorrect":len(resolved)-good,"accuracy":round(100*good/len(resolved),2),"brier":round(bs,4) if bs is not None else None,"binary_probability_n":len(binary)}
def main():
    if not SRC.exists(): raise SystemExit(f"Missing {SRC}")
    rows=list(csv.DictReader(SRC.open(encoding="utf-8"))); enriched=[]
    for i,r in enumerate(rows):
        z,lead,price,align,pers,accel,analog=state_score(rows,i); x=z*2.5
        enriched.append({**r,"phase33_raw_score":z,"phase33_x":x,"phase33_leading":lead,"phase33_price":price,"phase33_alignment":align,"phase33_persistence":pers,"phase33_acceleration":accel,"phase33_analog_vote":analog})
    cut=max(30,int(len(enriched)*.70)); dev=enriched[:cut]; hold=enriched[cut:]
    model={}
    for h in ("4h","8h"):
        train=[r for r in dev if r.get(f"actual_{h}") in {"BULLISH","BEARISH"}]; xs=[r["phase33_x"] for r in train]; ys=[1 if r[f"actual_{h}"]=="BULLISH" else 0 for r in train]; a,b=fit_platt(xs,ys); model[h]=(a,b)
        for r in enriched: r[f"phase33_probability_{h}"]=round(100*sigmoid(a*r["phase33_x"]+b),1)
    fields=list(enriched[0].keys());
    # A6: sealed-artifact guard. Default run writes to a non-canonical run dir.
    with guarded_output_path(OUT).open("w",newline="",encoding="utf-8") as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(enriched)
    hold_metrics={h:metrics(hold,f"phase33_probability_{h}",h) for h in ("4h","8h")}; dev_metrics={h:metrics(dev,f"phase33_probability_{h}",h) for h in ("4h","8h")}
    base_hold={h:base_metrics(hold,h) for h in ("4h","8h")}; base_all={h:base_metrics(enriched,h) for h in ("4h","8h")}
    # Approval requires directional accuracy OR Brier improvement on BOTH horizons and adequate n; deliberately strict.
    improves=[]
    for h in ("4h","8h"):
        m=hold_metrics[h]; b=base_hold[h]; improves.append(m.get("n",0)>=40 and ((m.get("accuracy",0)>b.get("accuracy",0)+1.0) or (m.get("brier",1)<b.get("brier",1)-0.005)))
    approved=all(improves)
    cal={"version":"phase33-platt-1","approved":approved,"a":round((model["4h"][0]+model["8h"][0])/2,6),"b":round((model["4h"][1]+model["8h"][1])/2,6),"fit_partition":"development_first_70_percent_only","holdout_used_for_fit":False,"approval_rule":"must improve both horizons under strict rule","holdout_metrics":hold_metrics,"base_holdout":base_hold}
    _cal=guarded_output_path(CAL); _cal.parent.mkdir(parents=True,exist_ok=True); _cal.write_text(json.dumps(cal,indent=2),encoding="utf-8")
    summary={"ok":True,"phase":"PHASE 33 INSTITUTIONAL PRE-MOVE","rows":len(enriched),"development_rows":len(dev),"untouched_holdout_rows":len(hold),"dev":dev_metrics,"holdout":hold_metrics,"base_holdout":base_hold,"base_all":base_all,"calibration_approved_for_live_probability":approved,"missing_historical_optional_inputs":["L2/L3","VIX/VXN intraday","US2Y/real-yield intraday","dealer gamma","options skew","ETF flow","volume delta","futures basis"],"missing_policy":"MISSING_NOT_FAKED_AND_NO_NEUTRAL_IMPUTATION","rl_influence_on_live":0.0,"broker_execution":False,"claim_95_percent":False,"note":"Replay is point-in-time over the preserved Phase29 forecast/evidence rows. Optional institutional feeds absent from the historical archive are explicitly excluded, not fabricated."}
    guarded_output_path(SUM).write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
if __name__=="__main__": main()
