from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from .models import CriticView, SpecialistView, RegimeView
from .utils import clamp

CORRELATED_GROUPS = {
    "tech_internal_cluster": {"Mega-cap Leadership AI", "Semiconductor AI", "Breadth/Internals AI"},
    "price_confirmation_cluster": {"Price Structure AI", "Multi-timeframe Trend AI", "NQ/ES/SPX Confirmation AI"},
    "macro_pressure_cluster": {"Rates & Yield AI", "Genuine Dollar/DXY AI", "Macro Surprise AI", "Fed Communication AI"},
}


def run_critic(specialists: List[SpecialistView], regime: RegimeView,
               hypotheses: Dict[str, Any], proposed_probability: float,
               data_coverage: float, intelligence_coverage: float,
               news_analysis: Dict[str, Any] | None = None) -> CriticView:
    objections: List[str] = []
    reinvestigate: List[str] = []
    correlated: List[str] = []
    severity_score = 0.0

    available = [s for s in specialists if s.reliability > 0]
    missing = [s for s in specialists if s.direction == "MISSING"]
    if len(available) < 9:
        objections.append(f"Only {len(available)} specialist brains have usable evidence; the rest are missing.")
        severity_score += .20
    critical_missing = [s for s in missing if s.family in {"macro_event","macro_market","price","cross_market"}]
    if critical_missing:
        reinvestigate.extend(s.name for s in critical_missing)
        objections.append("Critical context is missing: " + ", ".join(s.name for s in critical_missing[:5]))
        severity_score += min(.28, .07 * len(critical_missing))

    if data_coverage < .75:
        objections.append(f"Data coverage is only {data_coverage:.0%}; confidence must be constrained.")
        severity_score += .18
    if intelligence_coverage < .60:
        objections.append(f"Intelligence coverage is only {intelligence_coverage:.0%}; evidence diversity is limited.")
        severity_score += .15

    bull_strength = float((hypotheses.get("bullish_hypothesis") or {}).get("strength") or 0.0)
    bear_strength = float((hypotheses.get("bearish_hypothesis") or {}).get("strength") or 0.0)
    if bull_strength > 0 and bear_strength > 0:
        conflict_ratio = min(bull_strength, bear_strength) / max(bull_strength, bear_strength)
        if conflict_ratio >= .65:
            objections.append(f"Counter-case is strong ({conflict_ratio:.0%} of dominant case); one-sided confidence is not justified.")
            severity_score += .24
            reinvestigate.append("contradictory evidence")
        elif conflict_ratio >= .45:
            objections.append(f"Counter-case is material ({conflict_ratio:.0%} of dominant case).")
            severity_score += .12

    by_name = {s.name:s for s in specialists}
    for group, names in CORRELATED_GROUPS.items():
        members = [by_name[n] for n in names if n in by_name and by_name[n].reliability > .4 and abs(by_name[n].score) > .20]
        if len(members) >= 3:
            signs = {1 if m.score > 0 else -1 for m in members}
            if len(signs) == 1:
                correlated.append(group)
                objections.append(f"{group} contains multiple correlated confirmations; fusion must cap double-counting.")
                severity_score += .06

    if regime.primary == "CONFLICTED" and abs(proposed_probability - 50.0) >= 15.0:
        objections.append("Proposed probability is too decisive for a conflicted regime.")
        severity_score += .18
    if regime.primary == "MACRO_EVENT" and by_name.get("Macro Surprise AI", None) and by_name["Macro Surprise AI"].direction == "MISSING":
        objections.append("Macro-event regime detected without verified macro surprise data.")
        severity_score += .25
        reinvestigate.append("point-in-time macro source")

    if news_analysis:
        contradictions = news_analysis.get("contradictions") or []
        if contradictions:
            objections.append(f"News layer contains {len(contradictions)} duplicate-cluster contradiction(s).")
            severity_score += min(.15, len(contradictions)*.05)
            reinvestigate.append("primary-source news verification")
        primary_ratio = float(news_analysis.get("primary_source_ratio") or 0.0)
        if news_analysis.get("article_count", 0) >= 5 and primary_ratio < .10:
            objections.append("News evidence is mostly secondary; high-impact claims need primary-source confirmation.")
            severity_score += .08

    severity_score = clamp(severity_score)
    severity = "CRITICAL" if severity_score >= .70 else "HIGH" if severity_score >= .48 else "MEDIUM" if severity_score >= .25 else "LOW"
    hard_hold = severity == "CRITICAL" or (regime.primary == "MACRO_EVENT" and "point-in-time macro source" in reinvestigate)
    penalty = min(.45, severity_score * .45)
    return CriticView(
        severity=severity, score=round(severity_score,3), objections=objections or ["No material integrity objection detected."],
        reinvestigate=sorted(set(reinvestigate)), correlated_groups=correlated,
        reliability_penalty=round(penalty,3), hard_hold=hard_hold,
    )
