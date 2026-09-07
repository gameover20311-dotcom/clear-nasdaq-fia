from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
from .phase33_common import fnum, clamp, sigmoid, signal_map, raw_snapshot, dt
from .premove_max_engine import analyze_premove_max, DEFAULT_MAX_HISTORY
from .premove_engine import DEFAULT_HISTORY, _history_read, snapshot_row
from .phase33_institutional import collect_institutional_inputs
from .phase33_orderflow import analyze_orderflow
from .phase33_regime import detect_advanced_regime
from .phase33_news import analyze_news
from .phase33_analogs import nearest_outcome_analogs
from .phase33_risk import black_swan_guard, prop_guardrail, monte_carlo_risk_diagnostic
from .phase33_execution_sim import smart_order_routing_simulation
from .phase33_rl import rl_live_gate
from .phase33_rust import rust_status
from .phase33_event import event_surprise
from .phase33_crossasset import cross_asset_impulse

DATA_DIR=Path(__file__).resolve().parents[1]/"fia_phase33"/"data"
HISTORY=DATA_DIR/"phase33_history.jsonl"
CALIBRATION=DATA_DIR/"phase33_calibration.json"


def _append(row:Dict[str,Any],min_seconds:int=120)->bool:
    HISTORY.parent.mkdir(parents=True,exist_ok=True)
    old=[]
    if HISTORY.exists():
        try: old=[json.loads(x) for x in HISTORY.read_text().splitlines() if x.strip()]
        except Exception: old=[]
    if old and abs((dt(row["timestamp"])-dt(old[-1].get("timestamp"))).total_seconds())<min_seconds: return False
    with HISTORY.open("a",encoding="utf-8") as f: f.write(json.dumps(row,separators=(",",":"),sort_keys=True)+"\n")
    return True


def _row_from_forecast(forecast:Any,snapshot:Any)->Dict[str,Any]:
    r=snapshot_row(forecast,snapshot); r["regime"]=str(getattr(forecast,"regime",r.get("regime","UNKNOWN"))); return r


def _megacap_semi_decomp(forecast:Any)->Dict[str,Any]:
    sm=signal_map(forecast); mega=sm.get("Mega-cap leadership"); semi=sm.get("Semiconductors")
    return {"mega_cap_index_impact":{"status":"AVAILABLE" if mega else "MISSING_NOT_FAKED","score":mega.get("score") if mega else None},"semiconductor_breadth":{"status":"AVAILABLE" if semi else "MISSING_NOT_FAKED","score":semi.get("score") if semi else None}}


def _calibrate(raw_bull:float)->Dict[str,Any]:
    if CALIBRATION.exists():
        try:
            m=json.loads(CALIBRATION.read_text());
            if m.get("approved"):
                a=fnum(m.get("a"),1.0); b=fnum(m.get("b"),0.0); x=(raw_bull-50.0)/12.5; p=100*sigmoid(a*x+b)
                return {"status":"OOS_CALIBRATED","bullish":round(p,1),"bearish":round(100-p,1),"model_version":m.get("version")}
        except Exception: pass
    return {"status":"UNVALIDATED_DECISION_SCORE_NOT_PROBABILITY","bullish":None,"bearish":None,"raw_candidate_bullish":round(raw_bull,1)}


def analyze_phase33(forecast:Any,snapshot:Any,record:bool=True)->Dict[str,Any]:
    base=analyze_premove_max(forecast,snapshot,record=False)
    hist=_history_read(Path(DEFAULT_HISTORY)); cur=_row_from_forecast(forecast,snapshot)
    inst=collect_institutional_inputs(forecast,snapshot); flow=analyze_orderflow(snapshot); news=analyze_news(snapshot); event_sur=event_surprise(snapshot); cross=cross_asset_impulse(snapshot)
    adv_reg=detect_advanced_regime(hist,fnum(cur.get("leading_score")),fnum(cur.get("price_score")))
    replay_row={"timestamp":cur.get("timestamp"),"bullish_probability":cur.get("bullish_probability"),"confidence":cur.get("confidence"),"score":cur.get("score"),"regime":cur.get("regime"),"signals_json":json.dumps([{"name":k,"score":v["score"]} for k,v in signal_map(forecast).items()])}
    analog=nearest_outcome_analogs(cur.get("timestamp"),replay_row)
    decomp=_megacap_semi_decomp(forecast); rl=rl_live_gate(); rust=rust_status(); raw=raw_snapshot(snapshot)
    # Ensemble is availability-aware; missing institutional/order-flow inputs cannot vote neutral.
    votes=[]
    bdir=1 if base.get("direction")=="BULLISH" else -1 if base.get("direction")=="BEARISH" else 0
    if bdir: votes.append(("phase32",bdir,0.30))
    if flow.get("status")=="AVAILABLE" and abs(fnum(flow.get("score")))>=0.08: votes.append(("orderflow",1 if fnum(flow.get("score"))>0 else -1,0.12))
    mega=(decomp["mega_cap_index_impact"].get("score")); semi=(decomp["semiconductor_breadth"].get("score"))
    for n,v,w in (("mega",mega,0.12),("semi",semi,0.10)):
        if v is not None and abs(fnum(v))>=0.08: votes.append((n,1 if fnum(v)>0 else -1,w))
    nbr=analog.get("observed_bullish_rate_4h")
    if nbr is not None and abs(nbr-0.5)>=0.08: votes.append(("analogs",1 if nbr>0.5 else -1,0.12))
    if news.get("sentiment_score") is not None and abs(fnum(news.get("sentiment_score")))>=0.08: votes.append(("news",1 if fnum(news.get("sentiment_score"))>0 else -1,0.08))
    if event_sur.get("surprise_score") is not None and abs(fnum(event_sur.get("surprise_score")))>=0.08: votes.append(("event_surprise",1 if fnum(event_sur.get("surprise_score"))>0 else -1,0.08))
    if cross.get("score") is not None and abs(fnum(cross.get("score")))>=0.08: votes.append(("cross_asset",1 if fnum(cross.get("score"))>0 else -1,0.08))
    # Regime contributes confidence, not direction, unless price/lead direction is already established.
    total=sum(w for _,_,w in votes); signed=sum(s*w for _,s,w in votes)/total if total else 0.0
    agreement=(sum(w for _,s,w in votes if s==(1 if signed>=0 else -1))/total if total else 0.0)
    base_strength=fnum(base.get("decision_strength_0_100"))/100.0
    coverage=inst.get("coverage",0.0); missing_penalty=max(0.0,0.35-0.25*coverage)
    candidate=clamp(0.52*base_strength+0.28*abs(signed)+0.20*agreement-missing_penalty,0,1)
    direction="BULLISH" if signed>0.08 else "BEARISH" if signed<-0.08 else str(base.get("direction") or "NEUTRAL")
    raw_bull=50+(1 if direction=="BULLISH" else -1 if direction=="BEARISH" else 0)*candidate*42
    calibrated=_calibrate(raw_bull)
    shield=black_swan_guard(snapshot,inst,news); prop=prop_guardrail(snapshot)
    event=(base.get("event_context") or {}).get("event_risk")
    no_edge=(base.get("state")=="NO_EDGE" or agreement<0.55 or shield.get("triggered") or prop.get("breach") or event=="IMMINENT")
    state="NO_EDGE" if no_edge else "PHASE33_HIGH_ALIGNMENT" if candidate>=0.72 and agreement>=0.72 else "PHASE33_PREMOVE_THESIS" if candidate>=0.52 else "PHASE33_EARLY_WARNING"
    alert_fire=state in {"PHASE33_PREMOVE_THESIS","PHASE33_HIGH_ALIGNMENT"} and bool((base.get("persistence_hysteresis") or {}).get("hysteresis",{}).get("confirmed")) and not shield.get("triggered") and not prop.get("breach")
    risk_prob=(calibrated.get("bullish") if calibrated.get("status")=="OOS_CALIBRATED" else 50.0)/100.0
    result={
      "ok":True,"module":"FIA PHASE33 INSTITUTIONAL PRE-MOVE","version":"33.0","research_only":True,"broker_execution":False,
      "generated_at":cur.get("timestamp"),"direction":direction,"state":state,"decision_strength_0_100":round(candidate*100,1),"calibrated_probability":calibrated,
      "phase32":base,"institutional_inputs":inst,"orderflow_l2_l3":flow,"advanced_regime":adv_reg,"news_intelligence":news,"event_surprise":event_sur,"cross_asset_impulse":cross,
      "historical_outcome_analogs":analog,"leadership_decomposition":decomp,"rl_research":rl,"rust_acceleration":rust,
      "websocket_stream":{"endpoint":"/api/phase33/stream","polling_required":False},
      "execution_research":smart_order_routing_simulation(snapshot),"risk_research":monte_carlo_risk_diagnostic(risk_prob),
      "black_swan_shield":shield,"prop_firm_guardrail":prop,
      "ensemble":{"votes":[{"expert":n,"vote":"BULLISH" if s>0 else "BEARISH","weight":w} for n,s,w in votes],"signed_score":round(signed,4),"agreement":round(agreement,3),"active_experts":len(votes)},
      "alert":{"fire":alert_fire,"severity":"HIGH" if state=="PHASE33_HIGH_ALIGNMENT" and alert_fire else "MEDIUM" if alert_fire else "NONE","lead_time_status":"REQUIRES_FORWARD_VALIDATION"},
      "validation_gate":{"oos_required":True,"no_95_percent_claim_without_evidence":True,"no_holdout_threshold_tuning":True,"missing_data_never_faked":True},
      "frontend":{"dashboard":"/phase33","voice_copilot":True,"webgl_vol_surface":True,"interactive_replay":True},
    }
    if record:
        result["history_record_created"]=_append({"timestamp":cur.get("timestamp"),"direction":direction,"state":state,"strength":round(candidate*100,1),"agreement":round(agreement,3)})
    return result
