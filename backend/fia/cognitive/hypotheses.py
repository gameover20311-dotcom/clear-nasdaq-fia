from __future__ import annotations

from typing import Any, Dict, List

from .models import SpecialistView, RegimeView

REGIME_FOCUS = {
    "TREND": {"price", "equity_internal", "cross_market"},
    "MACRO_EVENT": {"macro_market", "macro_event", "event"},
    "EARNINGS_LED": {"event", "equity_internal", "price"},
    "HIGH_VOLATILITY": {"derivatives", "microstructure", "macro_market", "price"},
    "RANGE": {"microstructure", "cross_market", "price"},
    "CONFLICTED": {"cross_market", "macro_market", "event", "regime"},
    "TRANSITION": {"cross_market", "price", "macro_market", "equity_internal"},
}


def _importance(view: SpecialistView, regime: RegimeView) -> float:
    focus = REGIME_FOCUS.get(regime.primary, set())
    regime_bonus = 1.18 if view.family in focus else 1.0
    return abs(view.score) * view.reliability * regime_bonus


def build_hypotheses(specialists: List[SpecialistView], regime: RegimeView) -> Dict[str, Any]:
    ranked = sorted(
        [s for s in specialists if s.reliability > 0 and s.direction in {"BULLISH","BEARISH","NEUTRAL"}],
        key=lambda s: _importance(s, regime), reverse=True,
    )
    bullish = [s for s in ranked if s.score > .08]
    bearish = [s for s in ranked if s.score < -.08]
    neutral = [s for s in ranked if abs(s.score) <= .08]

    def case(items: List[SpecialistView], direction: str) -> Dict[str, Any]:
        strength = sum(_importance(x, regime) for x in items)
        return {
            "direction": direction,
            "strength": round(strength, 4),
            "evidence": [
                {"specialist": x.name, "score": x.score, "reliability": x.reliability,
                 "importance": round(_importance(x, regime), 4), "reason": x.reason}
                for x in items[:7]
            ],
        }

    bull_case = case(bullish, "BULLISH")
    bear_case = case(bearish, "BEARISH")
    dominant = "BULLISH" if bull_case["strength"] >= bear_case["strength"] else "BEARISH"
    counter = bear_case if dominant == "BULLISH" else bull_case
    investigation = []
    missing = [s for s in specialists if s.direction == "MISSING"]
    for s in missing:
        if s.family in REGIME_FOCUS.get(regime.primary, set()):
            investigation.append({"priority":"HIGH","specialist":s.name,"reason":s.missing_reason})
    if bull_case["strength"] > 0 and bear_case["strength"] > 0:
        ratio = min(bull_case["strength"], bear_case["strength"]) / max(bull_case["strength"], bear_case["strength"])
        if ratio >= .55:
            investigation.append({"priority":"HIGH","specialist":"Independent Critic","reason":"Bullish and bearish hypotheses are both materially supported; contradiction loop required."})
    return {
        "bullish_hypothesis": bull_case,
        "bearish_hypothesis": bear_case,
        "dominant_hypothesis": dominant,
        "counter_case": counter,
        "neutral_evidence": [x.name for x in neutral[:5]],
        "evidence_importance_order": [x.name for x in ranked],
        "controlled_investigation_queue": investigation,
        "policy": "Evidence importance is selected from reliability × directional strength × regime relevance; no outcome label is consulted.",
    }
