from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import SpecialistView
from .utils import as_float, clamp, clamp_signal, score_to_probability


def _forecast_dict(forecast: Any) -> Dict[str, Any]:
    if hasattr(forecast, "model_dump"):
        return forecast.model_dump()
    if hasattr(forecast, "dict"):
        return forecast.dict()
    if isinstance(forecast, dict):
        return dict(forecast)
    return dict(getattr(forecast, "__dict__", {}) or {})


def _signal_map(forecast: Any) -> Dict[str, Dict[str, Any]]:
    fc = _forecast_dict(forecast)
    out = {}
    for signal in fc.get("signals", []) or []:
        if not isinstance(signal, dict):
            signal = getattr(signal, "__dict__", {}) or {}
        if signal.get("name"):
            out[str(signal["name"])] = signal
    return out


def _active(signal: Optional[Dict[str, Any]]) -> bool:
    if not signal:
        return False
    freshness = str(signal.get("freshness") or "unknown").lower()
    return not any(x in freshness for x in ("missing", "unavailable", "error", "failed", "none"))


# ---------------------------------------------------------------- V6.6.5
# SESSION-AWARE FRESHNESS GATE FOR THE COGNITIVE / THREE-BRAIN EVIDENCE PATH.
#
# Before this, the cognitive layer only checked freshness WORDS ("missing",
# "error"). It never checked AGE. Verified on 2026-09-07T02:28Z, ^VIX was 54.3h
# old, carried freshness "delayed", and was still feeding Volatility & Options AI
# at reliability 0.65 as though it were current information.
#
# The gate below reuses the same session model as the pre-move layer, so a
# cash-session instrument is judged against ITS OWN venue: during a weekend a
# Friday print is CURRENT_FOR_SESSION and admissible; during an open session the
# same age is STALE and the specialist fails closed to MISSING. A stale input is
# never substituted with a neutral 50 — MISSING carries reliability 0.0 and
# uncertainty 1.0, and the raw value is preserved in missing_reason for audit.
SPECIALIST_SOURCE = {
    "Price Structure AI": "candles",
    "Multi-timeframe Trend AI": "candles",
    "NQ/ES/SPX Confirmation AI": "market_quotes",
    "Mega-cap Leadership AI": "market_quotes",
    "Semiconductor AI": "market_quotes",
    "Breadth/Internals AI": "market_quotes",
    "Equal-weight Participation AI": "market_quotes",
    "Rates & Yield AI": "us10y",
    "Genuine Dollar/DXY AI": "dxy",
    "Volatility & Options AI": "volatility",
    "News Event AI": "news",
    "Macro Surprise AI": "macro",
    "Fed Communication AI": "macro",
    "Earnings & Guidance AI": "earnings",
    "Liquidity & Session AI": "liquidity",
}

# Live ceilings mirror the pre-move layer (cadence-matched, not one threshold).
SPECIALIST_AGE_CEILING = {
    "market_quotes": 1800.0, "candles": 5400.0, "dxy": 21600.0, "us10y": 21600.0,
    "volatility": 21600.0, "news": 43200.0, "macro": 86400.0, "earnings": 86400.0,
    "liquidity": 5400.0,
}


def _source_ages(raw: Dict[str, Any]) -> Dict[str, Optional[float]]:
    health = (raw or {}).get("source_health")
    out: Dict[str, Optional[float]] = {}
    if isinstance(health, dict):
        for k, v in health.items():
            if isinstance(v, dict):
                try:
                    a = v.get("age_seconds")
                    out[str(k)] = None if a is None else float(a)
                except (TypeError, ValueError):
                    out[str(k)] = None
    return out


def _freshness_gate(name: str, ages: Dict[str, Optional[float]]) -> Dict[str, Any]:
    """Session-aware admissibility for one specialist's backing source."""
    src = SPECIALIST_SOURCE.get(name)
    if not src:
        return {"usable": True, "reason": "NO_SOURCE_MAPPED", "source": None}
    ceiling = SPECIALIST_AGE_CEILING.get(src, 21600.0)
    age = ages.get(src)
    if age is None:
        # Unknown age on a price-critical source fails closed; slower feeds do not.
        critical = src in {"market_quotes", "candles"}
        return {"usable": not critical, "reason": "AGE_UNKNOWN", "source": src,
                "age_seconds": None, "freshness_state": "UNKNOWN_AGE"}
    try:
        from ..market_sessions import session_state
    except Exception:
        return {"usable": age <= ceiling, "reason": "SESSION_MODEL_UNAVAILABLE",
                "source": src, "age_seconds": age}
    st = session_state(src, age, ceiling)
    return {"usable": bool(st.get("usable")), "source": src,
            "age_seconds": round(age, 1), "freshness_state": st.get("freshness"),
            "venue": st.get("venue"), "market_open": st.get("market_open"),
            "reason": st.get("reason")}


def _make(name: str, family: str, score: Optional[float], reliability: float, reason: str,
          evidence_ids: Optional[List[str]] = None, missing_reason: Optional[str] = None,
          tags: Optional[List[str]] = None) -> SpecialistView:
    if score is None:
        return SpecialistView(
            name=name, family=family, direction="MISSING", score=0.0,
            probability_bullish=50.0, reliability=0.0, uncertainty=1.0,
            evidence_ids=evidence_ids or [], reason=reason,
            missing_reason=missing_reason or "required evidence unavailable", tags=tags or [],
        )
    s = clamp_signal(float(score))
    direction = "BULLISH" if s > 0.08 else "BEARISH" if s < -0.08 else "NEUTRAL"
    rel = clamp(reliability)
    return SpecialistView(
        name=name, family=family, direction=direction, score=round(s, 4),
        probability_bullish=round(score_to_probability(s), 2), reliability=round(rel, 3),
        uncertainty=round(1.0 - rel, 3), evidence_ids=evidence_ids or [],
        reason=reason, missing_reason=missing_reason, tags=tags or [],
    )


def _evidence_id_lookup(ledger: Dict[str, Any]) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for row in ledger.get("records", []) or []:
        if row.get("category") != "signal":
            continue
        detail = row.get("metadata") or {}
        name = None
        # signal name is embedded in checksum payload only, so derive via instrument/detail when possible
        raw_detail = str(detail.get("detail") or "")
        instrument = str(row.get("instrument") or "")
        for candidate in (
            "NQ structure", "SPX confirmation", "DXY", "US10Y", "Mega-cap leadership",
            "Semiconductors", "Equal-weight participation", "Breadth", "News", "Macro calendar", "Earnings/guidance",
        ):
            if candidate in raw_detail or instrument == {
                "NQ structure":"NQ/QQQ", "SPX confirmation":"SPX/SPY", "DXY":"DXY",
                "US10Y":"US10Y", "Mega-cap leadership":"NASDAQ-100 constituents",
                "Semiconductors":"NASDAQ semiconductors",
                "Equal-weight participation":"NASDAQ breadth", "Breadth":"NASDAQ breadth",
                "News":"NASDAQ news", "Macro calendar":"US macro", "Earnings/guidance":"NASDAQ earnings",
            }.get(candidate):
                name = candidate
                break
        if name:
            result.setdefault(name, []).append(str(row.get("evidence_id")))
    return result


def _chart_direction(chart: Dict[str, Any], *keys: str) -> Optional[float]:
    vals = []
    for key in keys:
        value = chart.get(key)
        if isinstance(value, dict):
            d = str(value.get("direction") or "").upper()
        else:
            d = str(chart.get(f"{key}_direction") or "").upper()
        if d == "BULLISH": vals.append(1.0)
        elif d == "BEARISH": vals.append(-1.0)
    if not vals:
        return None
    return sum(vals) / len(vals)


def build_specialists(snapshot: Dict[str, Any], forecast: Any, ledger: Dict[str, Any],
                      news_analysis: Optional[Dict[str, Any]] = None,
                      chart_analysis: Optional[Dict[str, Any]] = None) -> List[SpecialistView]:
    raw = snapshot.get("data", snapshot) if isinstance(snapshot, dict) else {}
    signals = _signal_map(forecast)
    ids = _evidence_id_lookup(ledger)
    chart = chart_analysis or raw.get("chart_analysis") or {}
    views: List[SpecialistView] = []

    def sig(name: str, invert: bool = False) -> Tuple[Optional[float], float]:
        row = signals.get(name)
        if not _active(row): return None, 0.0
        s = as_float(row.get("score"))
        if s is None: return None, 0.0
        if invert: s = -s
        freshness = str(row.get("freshness") or "unknown").lower()
        rel = 0.95 if freshness == "live" else 0.85 if freshness in {"fresh","recent","available"} else 0.65
        return s, rel

    nq, nqrel = sig("NQ structure")
    chart_structure = _chart_direction(chart, "htf_poi", "order_block", "fair_value_gap", "execution_confirmation")
    if nq is None and chart_structure is None:
        views.append(_make("Price Structure AI", "price", None, 0, "No independent structure evidence.", missing_reason="NQ/chart structure unavailable"))
    else:
        vals = [(nq, nqrel, 0.65), (chart_structure, 0.82, 0.35)]
        active = [(v,r,w) for v,r,w in vals if v is not None]
        score = sum(v*w for v,r,w in active)/sum(w for v,r,w in active)
        rel = sum(r*w for v,r,w in active)/sum(w for v,r,w in active)
        views.append(_make("Price Structure AI", "price", score, rel, "Combines live NQ/QQQ structure with independent chart structure.", ids.get("NQ structure"), tags=["independent_chart"]))

    spx, spxrel = sig("SPX confirmation")
    mtf_vals = [x for x in (nq, spx) if x is not None]
    views.append(_make("Multi-timeframe Trend AI", "price", sum(mtf_vals)/len(mtf_vals) if mtf_vals else None,
                       mean_rel := (nqrel + spxrel)/max(1, int(nq is not None)+int(spx is not None)) if mtf_vals else 0,
                       "Uses NQ structure and broad-index confirmation as a trend-state proxy.",
                       (ids.get("NQ structure", []) + ids.get("SPX confirmation", [])), missing_reason="trend inputs unavailable"))

    smt = _chart_direction(chart, "smt")
    conf_vals = [(spx, spxrel, .55), (smt, .88, .45)]
    active = [(v,r,w) for v,r,w in conf_vals if v is not None]
    views.append(_make("NQ/ES/SPX Confirmation AI", "cross_market",
                       sum(v*w for v,r,w in active)/sum(w for v,r,w in active) if active else None,
                       sum(r*w for v,r,w in active)/sum(w for v,r,w in active) if active else 0,
                       "Cross-market confirmation plus independent NQ/ES SMT when available.", ids.get("SPX confirmation"), missing_reason="SPX/SMT evidence unavailable"))

    mega, megarel = sig("Mega-cap leadership")
    views.append(_make("Mega-cap Leadership AI", "equity_internal", mega, megarel, "Impact-weighted leadership in the largest NASDAQ constituents.", ids.get("Mega-cap leadership")))
    semis, semirel = sig("Semiconductors")
    views.append(_make("Semiconductor AI", "equity_internal", semis, semirel, "AI/semiconductor leadership and participation.", ids.get("Semiconductors")))
    # Current BASE_FIA names this live signal "Equal-weight participation".
    # The cognitive layer was still looking only for the legacy "Breadth" label,
    # so Breadth/Internals AI was permanently MISSING even when the underlying
    # tracked-name participation signal was live.  Keep the legacy fallback for
    # historical replay packets, but prefer the current production label.
    breadth, brrel = sig("Equal-weight participation")
    breadth_evidence_ids = ids.get("Equal-weight participation")
    if breadth is None:
        breadth, brrel = sig("Breadth")
        breadth_evidence_ids = ids.get("Breadth")
    views.append(_make(
        "Breadth/Internals AI", "equity_internal", breadth, brrel,
        "Equal-weight participation across the tracked NASDAQ large-cap basket (not full-market breadth).",
        breadth_evidence_ids,
    ))

    rates, ratesrel = sig("US10Y", invert=True)
    views.append(_make("Rates & Yield AI", "macro_market", rates, ratesrel, "US10Y is translated into NASDAQ impact direction: rising yields are a headwind.", ids.get("US10Y"), tags=["inverse_impact"]))
    dxy, dxyrel = sig("DXY", invert=True)
    views.append(_make("Genuine Dollar/DXY AI", "macro_market", dxy, dxyrel, "DXY is treated as an inverse NASDAQ pressure channel and never substituted with Fed Funds.", ids.get("DXY"), tags=["inverse_impact","instrument_truth"]))

    macro, macrorel = sig("Macro calendar")
    macro_status = str(raw.get("macro_status") or "").lower()
    if macro is None or "missing" in macro_status or "unavailable" in macro_status:
        views.append(_make("Macro Surprise AI", "macro_event", None, 0, "Macro surprise requires point-in-time actual/consensus evidence.", missing_reason=f"macro context unavailable: {raw.get('macro_status') or 'missing'}"))
    else:
        surprise = as_float(raw.get("macro_surprise_score"), macro)
        views.append(_make("Macro Surprise AI", "macro_event", surprise, max(macrorel, .75), "Point-in-time macro event/surprise impact.", ids.get("Macro calendar")))

    fed_score = as_float(raw.get("fed_communication_score"))
    fed_reliability = .82
    if fed_score is None and news_analysis and news_analysis.get("available"):
        fed_items = [x for x in (news_analysis.get("articles") or []) if str(x.get("event_type") or "") == "fed"]
        if fed_items:
            weights = [max(.01, float(x.get("impact") or 0.0)) for x in fed_items]
            total = sum(weights)
            fed_score = sum(float(x.get("sentiment") or 0.0)*w for x,w in zip(fed_items,weights))/total if total else None
            primary = any(bool(x.get("is_primary_source")) for x in fed_items)
            fed_reliability = .86 if primary else .68
    if fed_score is None:
        # Never invent a Fed stance from a neutral macro placeholder.
        views.append(_make("Fed Communication AI", "macro_event", None, 0, "Requires identified Fed communication or policy text.", missing_reason="no verified Fed communication evidence"))
    else:
        views.append(_make("Fed Communication AI", "macro_event", fed_score, fed_reliability, "Fed communication parsed from verified provider evidence; primary-source confirmation raises reliability."))

    news_sig, newsrel = sig("News")
    if news_analysis and news_analysis.get("available"):
        news_sig = as_float(news_analysis.get("directional_score"), news_sig)
        primary_ratio = as_float(news_analysis.get("primary_source_ratio"), 0.0) or 0.0
        newsrel = min(.95, .55 + .25*primary_ratio + .15*min(1.0, (news_analysis.get("article_count") or 0)/10.0))
    views.append(_make("News Event AI", "event", news_sig, newsrel,
                       "Deduplicated event intelligence with source quality, novelty, relevance and priced-in checks.", ids.get("News"), missing_reason="no directional news evidence"))

    earnings, erel = sig("Earnings/guidance")
    if earnings is None and raw.get("earnings_events"):
        # Events without reported surprises are risk context, not directional votes.
        views.append(_make("Earnings & Guidance AI", "event", None, 0, "Upcoming events exist but no verified actual-vs-expectation surprise is available.", missing_reason="event risk only; no directional surprise"))
    else:
        views.append(_make("Earnings & Guidance AI", "event", earnings, erel, "Tracked constituent earnings/guidance impulse using only available actuals." , ids.get("Earnings/guidance")))

    liquidity = _chart_direction(chart, "liquidity_sweep", "session_context")
    liq_available = bool(raw.get("liquidity_evidence_available")) or liquidity is not None
    views.append(_make("Liquidity & Session AI", "microstructure", liquidity if liq_available else None,
                       .85 if liquidity is not None else .58 if liq_available else 0,
                       "Independent session/liquidity sweep-reclaim context; QQQ and NQ remain separated.", missing_reason="liquidity/session direction unavailable"))

    vix = as_float(raw.get("vix_signal"))
    if vix is None:
        vix_value = as_float(raw.get("vix_value"))
        if vix_value is not None:
            # Elevated volatility is generally a risk headwind; neutral band intentionally broad.
            vix = .25 if vix_value < 16 else 0.0 if vix_value < 22 else -.45 if vix_value < 30 else -.70
    put_call = as_float(raw.get("put_call_signal"))
    skew = as_float(raw.get("skew_signal"))
    vol_vals = [v for v in (vix, put_call, skew) if v is not None]
    views.append(_make("Volatility & Options AI", "derivatives", sum(vol_vals)/len(vol_vals) if vol_vals else None,
                       .72 if len(vol_vals) >= 2 else .58 if len(vol_vals) == 1 else 0,
                       "Uses VIX plus optional put/call and skew evidence; missing derivatives data never becomes neutral.", missing_reason="VIX/options evidence unavailable"))

    # A dedicated regime specialist is intentionally derived independently of the final fusion.
    base_regime = str(_forecast_dict(forecast).get("regime") or "UNKNOWN").upper()
    # V6.6.2 TRUTH FIX. This specialist previously received reliability 0.78 whenever a
    # regime LABEL existed, even with every underlying signal missing, and its score
    # defaulted to a concrete 0.0 rather than None. With all other specialists MISSING
    # it therefore became the only weighted voter and carried 100% of the fusion
    # weight on zero market data. Reliability must come from the INPUTS, not the label.
    _regime_inputs = [v for v in (nq, mega, breadth, spx) if v is not None]
    _regime_rel_inputs = [r for r in (nqrel, megarel, brrel, spxrel) if r]
    if not _regime_inputs:
        regime_score = None          # -> _make() emits a MISSING specialist, reliability 0
        regime_rel = 0.0
    else:
        if base_regime == "TREND":
            regime_score = clamp_signal((nq or 0.0)*.55 + (mega or 0.0)*.25 + (breadth or 0.0)*.20)
        elif base_regime == "CONFLICTED":
            regime_score = 0.0
        elif base_regime == "TRANSITION":
            regime_score = clamp_signal((nq or 0.0)*.5 + (spx or 0.0)*.5)
        else:
            regime_score = clamp_signal((nq or 0.0)*.5 + (mega or 0.0)*.3 + (breadth or 0.0)*.2)
        # Cap by the mean reliability of the inputs actually present, and by coverage.
        _mean_rel = (sum(_regime_rel_inputs)/len(_regime_rel_inputs)) if _regime_rel_inputs else 0.0
        regime_rel = min(.78 if base_regime != "UNKNOWN" else .4,
                         _mean_rel * (len(_regime_inputs)/4.0))
    views.append(_make("Market Regime AI", "regime", regime_score, regime_rel,
                       f"Independent regime-state interpretation anchored to base regime={base_regime}; "
                       f"derived from {len(_regime_inputs)}/4 available input signals.",
                       missing_reason="no regime input signals (NQ structure / mega-cap / breadth / SPX) available",
                       tags=[base_regime]))

    # ---- V6.6.5 session-aware freshness gate ----------------------------
    # Applied AFTER construction so each specialist's own reason survives, and
    # so the withheld score stays visible for provenance instead of vanishing.
    _ages = _source_ages(raw)
    gated: List[SpecialistView] = []
    for v in views:
        g = _freshness_gate(getattr(v, "name", ""), _ages)
        if g.get("usable") or getattr(v, "direction", "") == "MISSING":
            gated.append(v)
            continue
        gated.append(_make(
            v.name, v.family, None, 0.0,
            "Backing evidence failed the session-aware freshness gate.",
            evidence_ids=list(getattr(v, "evidence_ids", []) or []),
            missing_reason=(
                "STALE_EXCLUDED source=%s age=%ss state=%s market_open=%s "
                "withheld_score=%s | %s" % (
                    g.get("source"), g.get("age_seconds"), g.get("freshness_state"),
                    g.get("market_open"), getattr(v, "score", None), g.get("reason"))),
            tags=list(getattr(v, "tags", []) or []) + ["stale_excluded"],
        ))
    return gated
