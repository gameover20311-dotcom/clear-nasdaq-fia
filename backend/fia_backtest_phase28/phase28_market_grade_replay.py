#!/usr/bin/env python3
# PHASE28_MARKET_GRADE_REPLAY_V1
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fia.providers import ProviderHub
from fia.engine import build_forecast
from fia.accuracy_engine import build_accuracy_assessment
from fia.confluence_engine import build_confluence_assessment
from fia_backtest_phase21.full_backtest import (
    START, END,
    prefetch_news_pool, build_news_index, build_snapshot_cached,
)
from fia_backtest_phase28.phase28_data import (
    FuturesCache, NQ_CACHE, ES_CACHE, load_macro_cache, macro_context_asof,
)
from fia_backtest_phase28.historical_chart import build_historical_chart_analysis
from fia_backtest_phase28.truth_metrics import (
    integrity_flags,
    metric,
    resolved_bool,
)

UTC = timezone.utc
NEUTRAL_THRESHOLD_PCT = 0.05
MAX_ENTRY_STALENESS_MINUTES = 90
MAX_OUTCOME_STALENESS_MINUTES = 90
OUTDIR = Path(__file__).resolve().parent / "results"
CSV_OUT = OUTDIR / "phase28_market_grade_replay_1y.csv"
SUMMARY_OUT = OUTDIR / "phase28_market_grade_replay_1y_summary.json"


def truth(v: Any) -> bool:
    return resolved_bool(v) is True


def direction_from_move(move_pct: Any) -> Optional[str]:
    if move_pct is None:
        return None
    if move_pct > NEUTRAL_THRESHOLD_PCT:
        return "BULLISH"
    if move_pct < -NEUTRAL_THRESHOLD_PCT:
        return "BEARISH"
    return "NEUTRAL"


def serial_signal(s: Any) -> Dict[str, Any]:
    return {
        "name": getattr(s,"name",None), "score": getattr(s,"score",None),
        "weight": getattr(s,"weight",None), "freshness": getattr(s,"freshness",None),
    }


def select(rows, fn): return [r for r in rows if fn(r)]


def summarize(rows: List[Dict[str, Any]], audit: Dict[str, Any]) -> Dict[str, Any]:
    grade_counts=Counter(str(r.get("phase25_grade") or "UNKNOWN") for r in rows)
    p24_counts=Counter(str(r.get("phase24_grade") or "UNKNOWN") for r in rows)
    subsets={
        "all": rows,
        "phase24_eligible": select(rows, lambda r: truth(r.get("phase24_eligible"))),
        "phase25_A": select(rows, lambda r: str(r.get("phase25_grade"))=="A"),
        "phase25_A_plus": select(rows, lambda r: str(r.get("phase25_grade"))=="A+"),
        "phase25_A_plus_plus": select(rows, lambda r: str(r.get("phase25_grade"))=="A++"),
        "phase25_eligible": select(rows, lambda r: truth(r.get("phase25_eligible"))),
        "macro_event_context": select(rows, lambda r: truth(r.get("macro_high_impact"))),
    }
    performance={k:{"4h":metric(v,4),"8h":metric(v,8)} for k,v in subsets.items()}
    hold=[r for r in rows if str(r.get("timestamp") or "") >= "2026-05-01"]
    hold_p25=[r for r in hold if truth(r.get("phase25_eligible"))]
    monthly={}
    for r in rows:
        m=str(r.get("timestamp") or "")[:7]
        monthly.setdefault(m,[]).append(r)
    monthly_perf={m:{"n":len(v),"4h":metric(v,4),"8h":metric(v,8)} for m,v in sorted(monthly.items())}
    summary={
        "phase":"PHASE 28",
        "window":[START.isoformat(),END.isoformat()],
        "forecasts":len(rows),
        "performance":performance,
        "holdout_2026_05_onward":{"all":{"4h":metric(hold,4),"8h":metric(hold,8)},"phase25_eligible":{"4h":metric(hold_p25,4),"8h":metric(hold_p25,8)}},
        "phase24_grade_counts":dict(p24_counts),
        "phase25_grade_counts":dict(grade_counts),
        "monthly":monthly_perf,
        "data_audit":audit,
        "research_only":True,
        "broker_execution":False,
        "note":"Historical accuracy is not a guarantee of future performance. Phase28 is a point-in-time research replay.",
    }
    return summary


def write_csv(rows: List[Dict[str, Any]]):
    OUTDIR.mkdir(parents=True, exist_ok=True)
    fields=[
        "timestamp","predicted","bullish_probability","bearish_probability","confidence","score","regime","data_coverage","intelligence_coverage",
        "phase24_grade","phase24_eligible","phase24_agreement","phase24_conflict",
        "phase25_grade","phase25_eligible","confluence_score","confluence_completeness","confluence_alignment",
        "chart_direction","nq_contract","es_contract","chart_data_status",
        "outcome_provider","outcome_contract","entry_bar_end","entry_nq","entry_staleness_min",
        "nq_4h","outcome_4h_bar_end","outcome_4h_staleness_min",
        "nq_8h","outcome_8h_bar_end","outcome_8h_staleness_min",
        "actual_4h","actual_8h","correct_4h","correct_8h","move_4h_pct","move_8h_pct",
        "market_available","market_requested","dxy_source","us10y_source",
        "news_articles","news_directional","news_evidence","macro_source_status","macro_high_impact","macro_event_risk",
        "earnings_evidence","earnings_catalyst_risk","earnings_future_eps_used",
        "liquidity_contract","liquidity_evidence","signals_json","chart_json",
    ]
    with CSV_OUT.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)


async def run_replay(limit: Optional[int]=None):
    timestamps=[]; cur=START
    while cur<=END:
        if cur.weekday()<5: timestamps.append(cur)
        cur += timedelta(days=1)
    if limit: timestamps=timestamps[:limit]

    nq=FuturesCache(NQ_CACHE)
    es=FuturesCache(ES_CACHE)
    macro_payload=load_macro_cache()
    if not nq.available:
        raise SystemExit("❌ Strict replay cannot run: real Massive NQ 5m cache missing")

    hub=ProviderHub()
    print("=== PHASE 28 MARKET-GRADE POINT-IN-TIME REPLAY ===")
    print("window =", START.isoformat(), "->", END.isoformat())
    print("checkpoints =", len(timestamps))
    print("NQ 5m =", nq.provider, "bars =", nq.bar_count)
    print("ES 5m =", es.provider if es.available else "MISSING", "bars =", es.bar_count)
    print("macro calendar =", macro_payload.get("status"), "events =", len(macro_payload.get("events") or []))
    print("core forecast weights tuning = NONE")
    print("Phase24 tuning = NONE")
    print("Phase25 tuning = NONE")
    print()

    print("Loading reproducible Polygon archive + supplemental Finnhub news...")
    news_pool, news_sources = await prefetch_news_pool(hub, START, END)
    news_index, news_epochs = build_news_index(news_pool)
    print("indexed news =", len(news_index), "sources =", dict(news_sources))

    rows=[]; errors=[]
    market_full=0; future_eps=0; es_covered=0; macro_context_days=0
    chart_complete=[]

    for idx,target in enumerate(timestamps,1):
        try:
            entry_contract, entry_row, entry_stale = nq.last_completed(
                target, MAX_ENTRY_STALENESS_MINUTES
            )
            if entry_row is None:
                print(f"[{idx:03d}/{len(timestamps)}] {target.date()} | SKIP no fresh NQ entry")
                continue
            entry = float(entry_row["close"])
            entry_end = entry_row["timestamp"] + timedelta(minutes=5)
            snapshot=await build_snapshot_cached(target,hub,news_index,news_epochs)
            data=snapshot["data"]
            data["nq_futures_price"]=entry

            # Phase22 truth semantics: no fake neutral votes.
            directional_news=int(data.get("historical_news_directional") or 0)
            if directional_news <= 0:
                data["news"] = None
                data["news_status"] = "historical_unscored"
                data["news_scored_articles"] = 0
            else:
                data["news_status"] = "historical_scored"
                data["news_scored_articles"] = directional_news

            # Historical macro: real calendar context only. Directional macro is
            # intentionally missing until a separately validated surprise model exists.
            mctx=macro_context_asof(target, macro_payload)
            data.update(mctx)
            data["historical_macro_evidence"] = mctx["macro_status"]

            # Explicit source labels: Yahoo historical 1H is used by the existing
            # point-in-time market adapter for DXY / US10Y and market leadership.
            data["dxy_source"] = "Yahoo Finance DX-Y.NYB historical 1H"
            data["us10y_source"] = "Yahoo Finance ^TNX historical 1H"

            snapshot["status"]="HISTORICAL_PHASE28_STRICT_PTI"
            forecast=build_forecast(snapshot)
            acc=build_accuracy_assessment(forecast,snapshot)
            chart=build_historical_chart_analysis(target,forecast.direction,nq,es if es.available else None)
            con=build_confluence_assessment(forecast,acc,chart,snapshot)

            row4, stale4 = nq.last_completed_for_contract(
                entry_contract,
                target + timedelta(hours=4),
                MAX_OUTCOME_STALENESS_MINUTES,
            )
            row8, stale8 = nq.last_completed_for_contract(
                entry_contract,
                target + timedelta(hours=8),
                MAX_OUTCOME_STALENESS_MINUTES,
            )
            p4 = float(row4["close"]) if row4 else None
            p8 = float(row8["close"]) if row8 else None
            end4 = row4["timestamp"] + timedelta(minutes=5) if row4 else None
            end8 = row8["timestamp"] + timedelta(minutes=5) if row8 else None
            move4=((p4-entry)/entry*100.0) if p4 is not None and entry else None
            move8=((p8-entry)/entry*100.0) if p8 is not None and entry else None
            a4=direction_from_move(move4); a8=direction_from_move(move8)
            c4=(forecast.direction==a4) if a4 else None
            c8=(forecast.direction==a8) if a8 else None

            if int(data.get("provider_quotes_available") or 0) >= int(data.get("provider_quotes_requested") or 999): market_full += 1
            if data.get("earnings_future_eps_used"): future_eps += 1
            if chart.get("es_contract"): es_covered += 1
            if mctx.get("macro_high_impact"): macro_context_days += 1
            chart_complete.append(float(con.get("confluence_completeness") or 0.0))

            row={
                "timestamp":target.isoformat(),"predicted":forecast.direction,
                "bullish_probability":forecast.bullish_probability,"bearish_probability":forecast.bearish_probability,
                "confidence":forecast.confidence,"score":forecast.score,"regime":forecast.regime,
                "data_coverage":forecast.data_coverage,"intelligence_coverage":forecast.intelligence_coverage,
                "phase24_grade":acc.get("setup_grade"),"phase24_eligible":acc.get("research_eligible"),
                "phase24_agreement":(acc.get("evidence") or {}).get("agreement"),"phase24_conflict":(acc.get("evidence") or {}).get("conflict"),
                "phase25_grade":con.get("setup_grade"),"phase25_eligible":con.get("research_eligible"),
                "confluence_score":con.get("confluence_score"),"confluence_completeness":con.get("confluence_completeness"),"confluence_alignment":con.get("confluence_alignment"),
                "chart_direction":chart.get("direction"),"nq_contract":chart.get("nq_contract"),"es_contract":chart.get("es_contract"),"chart_data_status":chart.get("data_status"),
                "outcome_provider":nq.provider,"outcome_contract":entry_contract,
                "entry_bar_end":entry_end.isoformat(),"entry_nq":entry,"entry_staleness_min":entry_stale,
                "nq_4h":p4,"outcome_4h_bar_end":end4.isoformat() if end4 else None,"outcome_4h_staleness_min":stale4,
                "nq_8h":p8,"outcome_8h_bar_end":end8.isoformat() if end8 else None,"outcome_8h_staleness_min":stale8,
                "actual_4h":a4,"actual_8h":a8,"correct_4h":c4,"correct_8h":c8,"move_4h_pct":move4,"move_8h_pct":move8,
                "market_available":data.get("provider_quotes_available"),"market_requested":data.get("provider_quotes_requested"),
                "dxy_source":data.get("dxy_source"),"us10y_source":data.get("us10y_source"),
                "news_articles":data.get("historical_news_articles"),"news_directional":data.get("historical_news_directional"),"news_evidence":data.get("historical_news_evidence"),
                "macro_source_status":mctx.get("macro_source_status"),"macro_high_impact":mctx.get("macro_high_impact"),"macro_event_risk":mctx.get("macro_event_risk"),
                "earnings_evidence":data.get("historical_earnings_evidence"),"earnings_catalyst_risk":data.get("earnings_catalyst_risk"),"earnings_future_eps_used":data.get("earnings_future_eps_used"),
                "liquidity_contract":data.get("liquidity_contract"),"liquidity_evidence":data.get("nq_liquidity_evidence"),
                "signals_json":json.dumps([serial_signal(s) for s in forecast.signals],separators=(",",":")),
                "chart_json":json.dumps(chart,separators=(",",":"),default=str),
            }
            rows.append(row)
            print(f"[{idx:03d}/{len(timestamps)}] {target.date()} | {forecast.direction} {forecast.confidence:.1f}% | P24 {acc.get('setup_grade')} | P25 {con.get('setup_grade')} | 4H {c4} | 8H {c8}")
        except Exception as exc:
            errors.append({"timestamp":target.isoformat(),"error":repr(exc)})
            print(f"[{idx:03d}/{len(timestamps)}] {target.date()} | ERROR {exc!r}")

    if not rows:
        raise SystemExit("❌ Phase28 produced zero forecasts")
    write_csv(rows)
    n=len(rows)
    audit={
        "nq_5m_provider":nq.provider,"nq_5m_bars":nq.bar_count,
        "es_5m_provider":es.provider if es.available else "missing","es_5m_bars":es.bar_count,"es_checkpoint_coverage":round(es_covered/n,3),
        "market_full_checkpoint_coverage":round(market_full/n,3),
        "polygon_news_cache_present":(ROOT/"fia_backtest_phase20/data/polygon_news_20250901_20260831.json").exists(),
        "macro_calendar_status":macro_payload.get("status"),"macro_event_context_days":macro_context_days,
        "future_eps_used_count":future_eps,
        "mean_phase25_completeness":round(sum(chart_complete)/len(chart_complete),3) if chart_complete else 0.0,
        "errors":errors,
        "lookahead_policy":"Only completed bars and news/earnings available as-of timestamp. Upcoming macro actual hidden. Dominant futures contract selected from completed trailing 24h volume.",
        "outcome_policy":"Massive NQ 5m completed bars on the entry-time frozen contract; no Yahoo outcome helper and no future contract reselection.",
    }
    outcome_integrity = integrity_flags(rows)
    audit["outcome_integrity"] = outcome_integrity
    audit["outcome_source_coverage"] = round(
        sum(1 for row in rows if row.get("outcome_provider") == nq.provider) / n, 4
    )
    hard_truth = (
        nq.bar_count > 80000
        and audit["market_full_checkpoint_coverage"] >= 0.95
        and audit["polygon_news_cache_present"]
        and future_eps == 0
        and len(errors) <= max(2,int(0.02*n))
        and audit["outcome_source_coverage"] >= 0.99
        and outcome_integrity["scheduled_resolution"]["4h"]["resolution_rate"] >= 0.95
        and outcome_integrity["scheduled_resolution"]["8h"]["resolution_rate"] >= 0.95
        and not outcome_integrity["perfect_result_warning"]
    )
    full_market_grade = hard_truth and audit["es_checkpoint_coverage"] >= 0.90 and str(audit["macro_calendar_status"]) == "available"
    audit["core_real_data_pass"] = hard_truth
    audit["full_market_grade"] = full_market_grade
    audit["grade"] = "MARKET_GRADE" if full_market_grade else ("REAL_DATA_DEGRADED" if hard_truth else "FAIL")

    summary=summarize(rows,audit)
    SUMMARY_OUT.write_text(json.dumps(summary,indent=2),encoding="utf-8")

    print("\n============================================================")
    print("PHASE 28 ONE-YEAR RESULT")
    print("============================================================")
    for name,block in summary["performance"].items():
        print(name, "| 4H", block["4h"], "| 8H", block["8h"])
    print("holdout phase25 eligible =", summary["holdout_2026_05_onward"]["phase25_eligible"])
    print("phase24 grades =", summary["phase24_grade_counts"])
    print("phase25 grades =", summary["phase25_grade_counts"])
    print("data_grade =", audit["grade"])
    print("market_full_checkpoint_coverage =", audit["market_full_checkpoint_coverage"])
    print("ES_SMT_checkpoint_coverage =", audit["es_checkpoint_coverage"])
    print("macro_calendar_status =", audit["macro_calendar_status"])
    print("future_eps_used_count =", future_eps)
    print("errors =", len(errors))
    print("CSV =", CSV_OUT)
    print("SUMMARY =", SUMMARY_OUT)
    print("broker_execution_added = NO")
    print("forecast_weights_changed = NO")
    print("============================================================")
    if hard_truth:
        print("✅ PHASE 28 STRICT POINT-IN-TIME REPLAY PASS")
    else:
        print("❌ PHASE 28 DATA INTEGRITY FAIL — inspect summary; do not trust headline accuracy")
    if hard_truth and not full_market_grade:
        print("⚠️ REAL DATA REPLAY IS VALID BUT NOT FULL MARKET_GRADE because at least one optional institutional-grade context source is missing (typically ES SMT or historical macro calendar).")


async def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=None,help="Smoke-test first N checkpoints")
    args=ap.parse_args()
    await run_replay(args.limit)

if __name__=="__main__":
    asyncio.run(main())
