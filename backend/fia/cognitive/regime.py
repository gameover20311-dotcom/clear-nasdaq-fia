from __future__ import annotations

from typing import Any, Dict, List

from .models import RegimeView, SpecialistView
from .utils import as_float, clamp, mean, truthy


def detect_regime(snapshot: Dict[str, Any], forecast: Any, specialists: List[SpecialistView]) -> RegimeView:
    raw = snapshot.get("data", snapshot) if isinstance(snapshot, dict) else {}
    fc = forecast.model_dump() if hasattr(forecast, "model_dump") else forecast.dict() if hasattr(forecast, "dict") else dict(forecast or {})
    base = str(fc.get("regime") or "UNKNOWN").upper()
    by_name = {s.name: s for s in specialists}

    reasons: List[str] = []
    secondary: List[str] = []
    risk_state = "NORMAL"

    macro_active = truthy(raw.get("macro_high_impact")) or truthy(raw.get("macro_event_risk"))
    earnings_active = truthy(raw.get("earnings_catalyst_risk")) or (as_float(raw.get("earnings_upcoming_events"), 0.0) or 0.0) > 0
    vix = as_float(raw.get("vix_value"))

    directional = [s for s in specialists if s.direction in {"BULLISH", "BEARISH"} and s.reliability >= .45]
    bull_weight = sum(s.reliability * abs(s.score) for s in directional if s.direction == "BULLISH")
    bear_weight = sum(s.reliability * abs(s.score) for s in directional if s.direction == "BEARISH")
    total = bull_weight + bear_weight
    conflict = min(bull_weight, bear_weight) / max(total, 1e-9)
    directional_strength = abs(bull_weight - bear_weight) / max(total, 1e-9)

    if macro_active:
        primary = "MACRO_EVENT"
        risk_state = "EVENT_RISK"
        reasons.append("Verified high-impact macro-event context is active.")
    elif earnings_active and by_name.get("Earnings & Guidance AI") and by_name["Earnings & Guidance AI"].reliability > .4:
        primary = "EARNINGS_LED"
        reasons.append("Tracked earnings/guidance catalyst is active and evidenced.")
    elif vix is not None and vix >= 30:
        primary = "HIGH_VOLATILITY"
        risk_state = "HIGH_VOL"
        reasons.append(f"VIX is elevated ({vix:.1f}).")
    elif conflict >= .35:
        primary = "CONFLICTED"
        risk_state = "CONFLICT"
        reasons.append(f"Reliable specialist evidence is materially split (conflict={conflict:.0%}).")
    elif base == "TREND" and directional_strength >= .35:
        primary = "TREND"
        reasons.append("Base regime and independent specialist dispersion both support trend conditions.")
    elif base in {"BALANCED", "RANGE"} and directional_strength <= .25:
        primary = "RANGE"
        reasons.append("Directional evidence is weak and balanced.")
    elif base == "TRANSITION":
        primary = "TRANSITION"
        reasons.append("Base engine identifies a transition and specialist direction is not dominant enough to override it.")
    else:
        primary = base if base in {"TREND", "RANGE", "CONFLICTED", "TRANSITION"} else "TRANSITION"
        reasons.append(f"Regime inherited cautiously from validated base state ({base}).")

    if total > 0:
        if bull_weight > bear_weight * 1.45:
            secondary.append("RISK_ON")
        elif bear_weight > bull_weight * 1.45:
            secondary.append("RISK_OFF")
    if vix is not None:
        secondary.append("LOW_VOLATILITY" if vix < 16 else "HIGH_VOLATILITY" if vix >= 25 else "NORMAL_VOLATILITY")
    if macro_active and primary != "MACRO_EVENT": secondary.append("MACRO_EVENT")
    if earnings_active and primary != "EARNINGS_LED": secondary.append("EARNINGS_LED")

    available_rel = [s.reliability for s in specialists if s.reliability > 0]
    # V6.6.2 TRUTH FIX: the (1-conflict) term paid a flat +0.20 confidence for the
    # ABSENCE of conflict. With zero evidence there is nothing to conflict, so a
    # dataless regime scored 0.20 of unearned confidence. Scale the agreement term
    # by how much evidence actually exists -- silence is not agreement.
    _evidence_fraction = (len(available_rel) / len(specialists)) if specialists else 0.0
    confidence = clamp((mean(available_rel, .0) * .55)
                       + (directional_strength * .25)
                       + ((1 - conflict) * .20 * _evidence_fraction))
    return RegimeView(primary=primary, secondary=secondary, confidence=round(confidence, 3), reasons=reasons,
                      risk_state=risk_state)
