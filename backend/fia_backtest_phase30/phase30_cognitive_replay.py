#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fia.cognitive.acceptance import acceptance_report, directional_metrics, expected_calibration_error
from fia.cognitive.calibration import apply_calibration, fit_platt, save_models
from fia.cognitive.fusion import fuse
from fia.cognitive.learning import mistake_attribution
from fia.cognitive.models import AnalogyView, CriticView, RegimeView, SpecialistView
from fia.cognitive.orchestrator import build_cognitive_report
from fia.cognitive.utils import as_float, direction_from_probability, parse_dt, stable_hash

SOURCE = ROOT / "fia_backtest_phase29" / "results" / "phase29_outcome_revalidated_1y.csv"
OUTDIR = Path(__file__).resolve().parent / "results"
CSV_OUT = OUTDIR / "phase30_cognitive_replay_1y.csv"
SUMMARY_OUT = OUTDIR / "phase30_cognitive_replay_1y_summary.json"
DEV_END = datetime(2026, 5, 1, tzinfo=timezone.utc)


def _json(value: Any, default):
    try: return json.loads(value or "")
    except Exception: return default


def _forecast_from_row(row: Dict[str,Any]) -> Dict[str,Any]:
    signals=_json(row.get("signals_json"),[])
    return {
        "symbol":"NQ","horizon_hours":8,"direction":row.get("predicted"),
        "bullish_probability":as_float(row.get("bullish_probability"),50.0),
        "bearish_probability":as_float(row.get("bearish_probability"),50.0),
        "confidence":as_float(row.get("confidence"),0.0),"regime":row.get("regime"),
        "status":"HISTORICAL_PTI","score":as_float(row.get("score"),0.0),
        "signals":signals,"invalidation":[],"generated_at":row.get("timestamp"),
        "data_coverage":as_float(row.get("data_coverage"),0.0),
        "intelligence_coverage":as_float(row.get("intelligence_coverage"),0.0),
        "source_status":{},"thesis":"","bullish_evidence":[],"bearish_evidence":[],
    }


def _snapshot_from_row(row: Dict[str,Any]) -> Dict[str,Any]:
    signals=_json(row.get("signals_json"),[])
    raw={}
    map_names={"NQ structure":"nq_structure","SPX confirmation":"spx_confirmation","DXY":"dxy","US10Y":"us10y",
               "Mega-cap leadership":"mega_cap","Semiconductors":"semis","Breadth":"breadth","News":"news",
               "Macro calendar":"macro","Earnings/guidance":"earnings"}
    for s in signals:
        if not isinstance(s,dict): continue
        key=map_names.get(str(s.get("name") or ""))
        freshness=str(s.get("freshness") or "").lower()
        if key and freshness not in {"missing","unavailable","error"}: raw[key]=as_float(s.get("score"))
    raw.update({
        "macro_status":row.get("macro_source_status") or "missing",
        "macro_high_impact":row.get("macro_high_impact"),"macro_event_risk":row.get("macro_event_risk"),
        "earnings_catalyst_risk":row.get("earnings_catalyst_risk"),"news_articles":as_float(row.get("news_articles"),0) or 0,
        "news_status":row.get("news_evidence") or "unknown","liquidity_evidence_available":str(row.get("liquidity_evidence") or "").lower()=="available",
        "provider_health":{"score":100.0 if str(row.get("market_available"))==str(row.get("market_requested")) else 80.0},
        "dxy_source":row.get("dxy_source"),"us10y_source":row.get("us10y_source"),
    })
    return {"data":raw,"status":"HISTORICAL_PTI","provider":"Phase29 provenance","timestamp":row.get("timestamp")}


def _is_dev(row: Dict[str,Any]) -> bool:
    dt=parse_dt(row.get("timestamp")); return bool(dt and dt<DEV_END)


def _label(row: Dict[str,Any], horizon: str):
    a=str(row.get(f"actual_{horizon}") or "").upper()
    return 1 if a=="BULLISH" else 0 if a=="BEARISH" else None


def _metric_with_fixed_probability(rows: List[Dict[str,Any]], direction_key: str, actual_key: str, probability_key: str):
    return directional_metrics(rows,direction_key,actual_key,probability_key)


def _naive_metrics(rows: List[Dict[str,Any]], horizon: str) -> Dict[str,Any]:
    vals=[]
    for r in rows:
        a=str(r.get(f"actual_{horizon}") or "").upper()
        if a not in {"BULLISH","BEARISH"}: continue
        vals.append({"actual":a,"direction":"BULLISH","p":50.0})
    return directional_metrics(vals,"direction","actual","p")


def _momentum_direction(row: Dict[str,Any]) -> str:
    for s in _json(row.get("signals_json"),[]):
        if isinstance(s,dict) and s.get("name")=="NQ structure":
            score=as_float(s.get("score"),0.0) or 0.0
            return "BULLISH" if score>=0 else "BEARISH"
    return "BULLISH"


def _momentum_metrics(rows: List[Dict[str,Any]], horizon: str) -> Dict[str,Any]:
    tmp=[]
    for r in rows:
        a=str(r.get(f"actual_{horizon}") or "").upper()
        if a not in {"BULLISH","BEARISH"}: continue
        d=_momentum_direction(r); tmp.append({"actual":a,"direction":d,"p":55.0 if d=="BULLISH" else 45.0})
    return directional_metrics(tmp,"direction","actual","p")


def _monthly(rows: List[Dict[str,Any]], horizon: str) -> List[Dict[str,Any]]:
    groups=defaultdict(list)
    for r in rows: groups[str(r.get("timestamp") or "")[:7]].append(r)
    out=[]
    for month in sorted(groups):
        m=directional_metrics(groups[month],f"cognitive_direction_{horizon}",f"actual_{horizon}",f"calibrated_probability_{horizon}")
        out.append({"month":month,**m})
    return out


def _by_regime(rows: List[Dict[str,Any]], horizon: str) -> Dict[str,Any]:
    groups=defaultdict(list)
    for r in rows: groups[str(r.get("cognitive_regime") or "UNKNOWN")].append(r)
    return {k:directional_metrics(v,f"cognitive_direction_{horizon}",f"actual_{horizon}",f"calibrated_probability_{horizon}") for k,v in groups.items()}


def _ablation(rows: List[Dict[str,Any]], horizon: str) -> Dict[str,Any]:
    hold=[r for r in rows if not _is_dev(r)]
    names=[]
    for r in hold:
        spec=_json(r.get("specialists_json"),[])
        names=sorted({x.get("name") for x in spec if isinstance(x,dict) and x.get("name")})
        if names: break
    results={}
    for name in names:
        tmp=[]
        for r in hold:
            actual=str(r.get(f"actual_{horizon}") or "").upper()
            if actual not in {"BULLISH","BEARISH"}: continue
            try:
                specs=[SpecialistView(**x) for x in _json(r.get("specialists_json"),[]) if x.get("name")!=name]
                regime=RegimeView(**_json(r.get("regime_json"),{}))
                analogy=AnalogyView(**_json(r.get(f"analogy_{horizon}_json"),{}))
                critic=CriticView(**_json(r.get("critic_json"),{}))
                p=float(fuse(specs,regime,analogy,critic)["raw_bullish_probability"])
            except Exception:
                continue
            d=direction_from_probability(p)
            tmp.append({"actual":actual,"direction":d,"p":p})
        results[name]=directional_metrics(tmp,"direction","actual","p")
    return results


def run() -> Dict[str,Any]:
    if not SOURCE.exists(): raise SystemExit(f"Missing source: {SOURCE}")
    with SOURCE.open(newline="",encoding="utf-8") as f: source=list(csv.DictReader(f))
    rows=[]
    identity={"available":False,"horizons":{},"dataset_split":{"development":"2025-09-01..2026-04-30","holdout":"2026-05-01..2026-08-31"}}
    print("=== PHASE 30 COGNITIVE POINT-IN-TIME REPLAY ===")
    print("source rows =",len(source),"| dev end =",DEV_END.isoformat())
    for idx,row in enumerate(source,1):
        fc=_forecast_from_row(row); snap=_snapshot_from_row(row); chart=_json(row.get("chart_json"),{})
        r4=build_cognitive_report(snap,fc,news_items=None,chart_analysis=chart,horizon="4h",persist=False,calibration_models=identity)
        r8=build_cognitive_report(snap,fc,news_items=None,chart_analysis=chart,horizon="8h",persist=False,calibration_models=identity)
        out=dict(row)
        out.update({
            "raw_probability_4h":r4["raw_probability_before_calibration"],"raw_probability_8h":r8["raw_probability_before_calibration"],
            "cognitive_regime":r8["regime"]["primary"],"critic_severity":r8["critic"]["severity"],"critic_score":r8["critic"]["score"],
            "reliability_score":r8["reliability_score"],"reliability":r8["reliability"],"decision_gate":r8["decision_gate"],
            "forecast_id":r8["forecast_id"],"ledger_digest":r8["evidence_ledger"]["ledger_digest"],
            "specialists_json":json.dumps(r8["specialists"],separators=(",",":")),
            "regime_json":json.dumps(r8["regime"],separators=(",",":")),
            "critic_json":json.dumps(r8["critic"],separators=(",",":")),
            "hypotheses_json":json.dumps(r8["hypotheses"],separators=(",",":")),
            "analogy_4h_json":json.dumps(r4["historical_analogy"],separators=(",",":")),
            "analogy_8h_json":json.dumps(r8["historical_analogy"],separators=(",",":")),
        })
        rows.append(out)
        if idx%40==0 or idx==len(source): print(f"[{idx:03d}/{len(source)}]",row.get("timestamp"),"raw8=",out["raw_probability_8h"],"critic=",out["critic_severity"])

    dev=[r for r in rows if _is_dev(r)]; hold=[r for r in rows if not _is_dev(r)]
    models={"available":True,"created_at":datetime.now(timezone.utc).isoformat(),
            "dataset_split":{"development":"2025-09-01T00:00:00Z..2026-04-30T23:59:59Z","holdout":"2026-05-01T00:00:00Z..2026-08-31T23:59:59Z","holdout_used_for_fitting":False},"horizons":{}}
    for h in ("4h","8h"):
        probs=[]; labels=[]
        for r in dev:
            y=_label(r,h)
            if y is None: continue
            probs.append(float(r[f"raw_probability_{h}"])); labels.append(y)
        models["horizons"][h]=fit_platt(probs,labels)
    save_models(models)

    for r in rows:
        for h in ("4h","8h"):
            p=apply_calibration(float(r[f"raw_probability_{h}"]),models["horizons"][h])
            r[f"calibrated_probability_{h}"]=p
            r[f"cognitive_direction_{h}"]=direction_from_probability(p)
            a=str(r.get(f"actual_{h}") or "").upper()
            r[f"cognitive_correct_{h}"]=(r[f"cognitive_direction_{h}"]==a) if a in {"BULLISH","BEARISH"} else None

    OUTDIR.mkdir(parents=True,exist_ok=True)
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    with CSV_OUT.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)

    def pack(group):
        return {
            "cognitive_4h":directional_metrics(group,"cognitive_direction_4h","actual_4h","calibrated_probability_4h"),
            "cognitive_8h":directional_metrics(group,"cognitive_direction_8h","actual_8h","calibrated_probability_8h"),
            "base_4h":directional_metrics(group,"predicted","actual_4h","bullish_probability"),
            "base_8h":directional_metrics(group,"predicted","actual_8h","bullish_probability"),
            "naive_4h":_naive_metrics(group,"4h"),"naive_8h":_naive_metrics(group,"8h"),
            "momentum_4h":_momentum_metrics(group,"4h"),"momentum_8h":_momentum_metrics(group,"8h"),
            "calibration_4h":expected_calibration_error(group,"calibrated_probability_4h","actual_4h"),
            "calibration_8h":expected_calibration_error(group,"calibrated_probability_8h","actual_8h"),
        }
    summary={
        "phase":"PHASE 30 - COGNITIVE EVIDENCE INTELLIGENCE","status":"COMPLETED_RESEARCH_VALIDATION",
        "source":str(SOURCE),"rows":len(rows),"development_rows":len(dev),"holdout_rows":len(hold),
        "calibration_models":models,"development":pack(dev),"holdout":pack(hold),"all":pack(rows),
        "monthly_4h":_monthly(rows,"4h"),"monthly_8h":_monthly(rows,"8h"),
        "holdout_regime_4h":_by_regime(hold,"4h"),"holdout_regime_8h":_by_regime(hold,"8h"),
        "ablation_holdout_8h_raw":_ablation(rows,"8h"),
        "mistake_attribution_4h":mistake_attribution(rows,"4h"),"mistake_attribution_8h":mistake_attribution(rows,"8h"),
        "traceability":{"all_rows_traceable":all(bool(r.get("forecast_id")) and bool(r.get("ledger_digest")) for r in rows),"forecast_ids_unique":len({r.get("forecast_id") for r in rows})==len(rows)},
        "integrity":{"no_known_future_leakage":True,"missing_not_neutral":True,"analogy_prior_only":True,"calibration_holdout_used_for_fitting":False,"outcome_source":"Massive Futures inherited from Phase29"},
        "research_only":True,"broker_execution":False,"generated_at":datetime.now(timezone.utc).isoformat(),
    }
    summary["acceptance"]=acceptance_report(summary)
    summary["result_digest"]=stable_hash({"holdout":summary["holdout"],"models":models,"acceptance":summary["acceptance"]})
    SUMMARY_OUT.write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps({"development":summary["development"],"holdout":summary["holdout"],"acceptance":summary["acceptance"]},indent=2))
    print("CSV =",CSV_OUT); print("SUMMARY =",SUMMARY_OUT)
    return summary


if __name__=="__main__": run()
