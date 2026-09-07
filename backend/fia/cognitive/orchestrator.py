from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .acceptance import wilson_interval
from .analogy import build_analogy
from .calibration import calibrate, load_models
from .critic import run_critic
from .drift import build_drift_status
from .fusion import fuse
from .hypotheses import build_hypotheses
from .investigation import execute_controlled_investigation
from .news_brain import analyze_news
from .provenance import build_evidence_ledger, persist_ledger, verify_ledger_chain
from .regime import detect_regime
from .reaction import annotate_market_reaction
from .specialists import build_specialists
from .utils import as_float, clamp, direction_from_probability, parse_dt, utc_now_iso


def _forecast_dict(forecast: Any) -> Dict[str, Any]:
    if hasattr(forecast, "model_dump"):
        return forecast.model_dump()
    if hasattr(forecast, "dict"):
        return forecast.dict()
    if isinstance(forecast, dict):
        return dict(forecast)
    return dict(getattr(forecast, "__dict__", {}) or {})


def _as_of(snapshot: Dict[str, Any], forecast: Any) -> str:
    fc = _forecast_dict(forecast)
    value = fc.get("generated_at") or snapshot.get("timestamp") or utc_now_iso()
    dt = parse_dt(value)
    return (dt or datetime.now(timezone.utc)).isoformat()


def _coverage(specialists) -> float:
    weights = {"price":1.2,"cross_market":1.1,"equity_internal":1.0,"macro_market":1.1,"macro_event":1.15,
               "event":1.0,"microstructure":.9,"derivatives":.7,"regime":.8}
    total=sum(weights.get(s.family,1.0) for s in specialists)
    available=sum(weights.get(s.family,1.0)*s.reliability for s in specialists)
    return clamp(available/total) if total else 0.0


def _reliability_grade(score: float) -> str:
    return "HIGH" if score>=.78 else "MEDIUM" if score>=.62 else "LOW" if score>=.45 else "LIMITED"


def build_cognitive_report(snapshot: Dict[str, Any], forecast: Any,
                           news_items: Optional[List[Dict[str, Any]]] = None,
                           chart_analysis: Optional[Dict[str, Any]] = None,
                           horizon: str = "8h", persist: bool = False,
                           calibration_models: Optional[Dict[str,Any]] = None) -> Dict[str, Any]:
    fc=_forecast_dict(forecast)
    as_of=_as_of(snapshot,forecast)
    news_analysis=analyze_news(news_items or [], parse_dt(as_of)) if news_items else {
        "available": False,
        "article_count": int((snapshot.get("data",snapshot) if isinstance(snapshot,dict) else {}).get("news_articles") or 0),
        "primary_source_ratio": 0.0,
        "directional_score": None,
        "contradictions": [],
        "policy": {"status":"SUMMARY_ONLY","note":"Deep article-level analysis requires normalized articles; missing detail is not treated as neutral."},
    }
    ledger=build_evidence_ledger(snapshot,forecast,news_items or [])
    specialists=build_specialists(snapshot,forecast,ledger,news_analysis,chart_analysis)
    regime=detect_regime(snapshot,forecast,specialists)
    hypotheses=build_hypotheses(specialists,regime)
    analogy=build_analogy(specialists,as_of,horizon=horizon)

    first=fuse(specialists,regime,analogy,None)
    raw_data=snapshot.get("data",snapshot) if isinstance(snapshot,dict) else {}
    data_cov=as_float(fc.get("data_coverage"),0.0) or 0.0
    specialist_cov=_coverage(specialists)
    critic=run_critic(specialists,regime,hypotheses,float(first["raw_bullish_probability"]),data_cov,specialist_cov,news_analysis)
    second=fuse(specialists,regime,analogy,critic)

    models=calibration_models or load_models()
    calibration=calibrate(float(second["raw_bullish_probability"]),horizon,models)
    p=float(calibration["calibrated_probability"])
    _raw_p=float(second["raw_bullish_probability"])

    # DIRECTION FOLLOWS THE EVIDENCE, NOT THE FITTED BASE RATE.
    # Measured on the untouched holdout window, the previous full-Platt intercept
    # flipped the sign relative to the raw evidence score on 26.0% of 4H rows and
    # 25.8% of 8H rows, and made Brier worse than applying no calibration at all.
    # Calibration may sharpen or shrink a probability; it must never decide the sign.
    # The calibrator is now slope-only (b pinned at 0), so a flip is mathematically
    # impossible -- this guard additionally makes that guarantee explicit and
    # auditable, and stays correct if a model with an intercept is ever reinstated.
    _raw_dir=direction_from_probability(_raw_p)
    _cal_dir=direction_from_probability(p)
    _flipped=bool(_raw_dir!=_cal_dir)
    direction=_raw_dir
    if _flipped:
        # Publish the evidence probability so the headline cannot contradict the
        # headline direction, and expose the calibrated value separately.
        p=_raw_p

    # V6.6.2 (L-1): the Platt transform carries a non-zero intercept, so a genuine
    # no-information raw probability of 50.0 was being rendered as a directional
    # 57.22% BULLISH headline (8h b=0.29091559 => +7.22 pts; 4h => +2.70 pts).
    # Calibration may refine a real estimate; it must never manufacture a direction
    # out of absent evidence. Detect the no-evidence state here and abstain.
    _specialists_with_evidence=sum(
        1 for s_ in specialists
        if getattr(s_,"direction","MISSING")!="MISSING" and float(getattr(s_,"reliability",0.0) or 0.0)>0.0
    )
    no_evidence=(_specialists_with_evidence==0) or (float(specialist_cov or 0.0)<=0.0)

    # Reliability is separate from probability and is penalized by the critic.
    calibration_available=bool((calibration.get("model") or {}).get("available"))
    analogy_rel=min(1.0,analogy.effective_sample_size/15.0)*analogy.mean_similarity if analogy.available else 0.0
    provider_health=raw_data.get("provider_health") or {}
    # V6.6.2 (L-3): an ABSENT provider-health score is not 60% healthy. Unknown
    # provider health now contributes zero instead of silently inflating reliability.
    _ph_status=str(raw_data.get("provider_health_status") or "").upper()
    _ph_raw=provider_health.get("score")
    if _ph_raw is None:
        provider_score=100.0 if _ph_status=="LIVE" else 0.0
        provider_health_known=(_ph_status=="LIVE")
    else:
        provider_score=as_float(_ph_raw,0.0) or 0.0
        provider_health_known=True
    reliability=(data_cov*.24 + specialist_cov*.28 + regime.confidence*.14 + min(1.0,provider_score/100)*.14 + analogy_rel*.10 + (.10 if calibration_available else .02))
    reliability *= (1.0-critic.reliability_penalty)
    reliability=clamp(reliability)

    hard_hold = critic.hard_hold or reliability < .43 or specialist_cov < .50
    decision_gate="RESEARCH HOLD — INSUFFICIENT RELIABILITY" if hard_hold else "RESEARCH ELIGIBLE"

    # V6.6.2: with no evidence at all there is no direction to report.
    if no_evidence:
        direction="NO_EDGE"
        p=50.0
        decision_gate="NO_EDGE — NO EVIDENCE AVAILABLE"
    # V6.6.2 (L-2): the previous interval was manufactured from the point estimate
    # itself -- pseudo_correct = round(p * effective_n) -- so it encoded no observed
    # outcomes whatsoever while presenting itself as an empirical 95% interval.
    # A confidence interval requires real resolved trials. When we do not have them,
    # the honest answer is UNAVAILABLE.
    _analogy_n=int(analogy.sample_size or 0) if analogy.available else 0
    _analogy_p=analogy.bullish_probability if analogy.available else None
    if _analogy_n>=5 and _analogy_p is not None:
        # Real observed outcomes: how many of the n resolved point-in-time analogues
        # actually resolved bullish. This is an empirical base-rate interval and is
        # labelled as such -- it is NOT an interval on this forecast's accuracy.
        _hits=int(round((float(_analogy_p)/100.0)*_analogy_n))
        interval=wilson_interval(_hits,_analogy_n)
        interval_basis=("wilson_95_on_%d_resolved_point_in_time_analogue_outcomes"
                        "__base_rate_not_forecast_accuracy"%_analogy_n)
    else:
        interval={"low":None,"high":None,"available":False,
                  "reason":"UNAVAILABLE: fewer than 5 resolved point-in-time analogues; "
                           "an empirical interval cannot be derived from the point estimate alone"}
        interval_basis="unavailable"
    effective_n=_analogy_n

    report={
        "ok": True,
        "system": "CLEAR NASDAQ — FIA COGNITIVE EVIDENCE INTELLIGENCE",
        "architecture_version": "30.0.0-cognitive",
        "forecast_id": ledger["forecast_id"],
        "as_of": as_of,
        "horizon": horizon,
        "direction": direction,
        "bullish_probability": round(p,2),
        "bearish_probability": round(100-p,2),
        "raw_probability_before_calibration": round(_raw_p,2),
        "calibrated_bullish_probability": round(float(calibration["calibrated_probability"]),2),
        "calibration_flips_direction": _flipped,
        "direction_basis": "raw_evidence_score__calibration_may_not_decide_sign",
        "published_probability_basis": ("raw_evidence__calibration_disagreed_on_sign"
                                        if _flipped else "calibrated"),
        "probability_interval_approx_95": interval,
        "probability_interval_basis": interval_basis,
        "no_evidence_abstention": bool(no_evidence),
        "provider_health_known": bool(provider_health_known),
        "reliability": _reliability_grade(reliability),
        "reliability_score": round(reliability,3),
        "decision_gate": decision_gate,
        "data_coverage": round(data_cov,3),
        "intelligence_coverage": round(specialist_cov,3),
        "base_forecast": {k:fc.get(k) for k in ("direction","bullish_probability","bearish_probability","confidence","regime","status","score")},
        "evidence_ledger": {k:v for k,v in ledger.items() if k!="records"},
        "evidence_records": ledger["records"],
        "news_intelligence": news_analysis,
        "specialists": [s.to_dict() for s in specialists],
        "regime": regime.to_dict(),
        "hypotheses": hypotheses,
        "historical_analogy": analogy.to_dict(),
        "fusion": second,
        "critic": critic.to_dict(),
        "calibration": calibration,
        "drift_monitor": build_drift_status(),
        "invalidation": fc.get("invalidation") or [],
        "missing_evidence": [s.to_dict() for s in specialists if s.direction=="MISSING"],
        "policy": {
            "research_only": True,
            "broker_execution": False,
            "unknown_is_not_neutral": True,
            "independent_bull_bear_hypotheses": True,
            "independent_critic": True,
            "point_in_time_analogy": True,
            "regime_dynamic_weights_are_audited": True,
            "automatic_weight_learning_without_oos_proof": False,
            "future_accuracy_guarantee": False,
        },
    }
    if persist:
        report["ledger_persistence"] = persist_ledger(ledger)
        report["ledger_chain"] = verify_ledger_chain()
    return report


async def build_deep_cognitive_report(hub: Any, snapshot: Dict[str, Any], forecast: Any,
                                      chart_analysis: Optional[Dict[str, Any]] = None,
                                      horizon: str = "8h", persist: bool = True) -> Dict[str, Any]:
    news_items=[]
    try:
        # Existing ProviderHub already normalizes, context-tags and duplicate-clusters news.
        news_items=await hub.unified_news_feed(company_days=3,market_limit=60,company_limit=20)
        try:
            news_items=hub.apply_news_trust_scores(news_items)
        except Exception:
            pass
        # Attach an observed post-publication QQQ reaction when candles are available.
        # This powers the priced-in check without asking the language model to guess.
        try:
            published = [parse_dt(x.get("published_at") or x.get("publishedAt") or x.get("datetime")) for x in news_items if isinstance(x, dict)]
            published = [x for x in published if x is not None]
            if published:
                start_ts = int((min(published)).timestamp())
                end_ts = int(datetime.now(timezone.utc).timestamp())
                candles = await hub.finnhub_candles("QQQ", "5", start_ts, end_ts)
                if candles:
                    news_items = annotate_market_reaction(news_items, candles, minutes_after=30)
        except Exception:
            pass
    except Exception as exc:
        news_items=[]
        warning=f"Deep news retrieval unavailable: {exc}"
    else:
        warning=None
    report=build_cognitive_report(snapshot,forecast,news_items,chart_analysis,horizon,persist)
    if warning:
        report.setdefault("warnings",[]).append(warning)

    # One bounded contradiction/research loop. A second report is built only if
    # the independent critic explicitly asks for reinvestigation.
    investigation = await execute_controlled_investigation(hub, report, report.get("as_of"))
    if investigation.get("triggered"):
        expanded_news = investigation.get("news_items") or news_items
        rerun = build_cognitive_report(snapshot, forecast, expanded_news, chart_analysis, horizon, persist=False)
        rerun["investigation_loop"] = {
            "triggered": True,
            "initial_critic": report.get("critic"),
            "executed": {k:v for k,v in investigation.items() if k != "news_items"},
            "critic_after_reinvestigation": rerun.get("critic"),
            "changed_direction": rerun.get("direction") != report.get("direction"),
            "probability_change_points": round(float(rerun.get("bullish_probability",50))-float(report.get("bullish_probability",50)),2),
        }
        # Keep the original persisted ledger id but expose the reinvestigated analysis.
        rerun["original_forecast_id"] = report.get("forecast_id")
        if report.get("ledger_persistence"):
            rerun["ledger_persistence"] = report.get("ledger_persistence")
            rerun["ledger_chain"] = report.get("ledger_chain")
        return rerun
    report["investigation_loop"] = {"triggered":False,"queue":investigation.get("queue",[])}
    return report
