# PHASE24_ACCURACY_ENGINE_V1
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
import csv

try:
    from .intelligence import nasdaq_impact_direction
except Exception:
    def nasdaq_impact_direction(name: str, direction: str) -> str:
        key = "".join(ch for ch in (name or "").lower() if ch.isalnum())
        raw = (direction or "").lower()
        inverse = {"dxy", "us10y"}
        if key in inverse:
            if raw == "bullish": return "Bearish"
            if raw == "bearish": return "Bullish"
        return "Bullish" if raw == "bullish" else "Bearish" if raw == "bearish" else "Neutral"


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _active_signal(signal: Any) -> bool:
    freshness = str(_get(signal, "freshness", "unknown") or "unknown").lower()
    return not any(x in freshness for x in ("missing", "error", "failed", "unavailable", "none"))


def evidence_alignment(forecast: Any) -> Dict[str, Any]:
    """Measure whether available evidence agrees with the final NASDAQ direction.

    This is an additive Phase 24 research-quality layer. It does not change the
    Phase 21 forecast direction, probability, confidence, or weights.
    """
    direction = str(_get(forecast, "direction", "") or "").upper()
    signals = list(_get(forecast, "signals", []) or [])

    aligned = 0.0
    opposed = 0.0
    neutral = 0.0
    aligned_names: List[str] = []
    opposed_names: List[str] = []
    missing_names: List[str] = []

    for signal in signals:
        name = str(_get(signal, "name", "") or "")
        if not _active_signal(signal):
            missing_names.append(name)
            continue

        score = _as_float(_get(signal, "score", 0.0))
        weight = max(0.0, _as_float(_get(signal, "weight", 0.0)))
        strength = min(1.0, abs(score))
        effective = weight * (0.50 + 0.50 * strength)

        if abs(score) <= 0.08:
            neutral += effective
            continue

        raw_direction = "bullish" if score > 0 else "bearish"
        impact_direction = str(nasdaq_impact_direction(name, raw_direction)).upper()

        if impact_direction == direction:
            aligned += effective
            aligned_names.append(name)
        elif impact_direction in {"BULLISH", "BEARISH"}:
            opposed += effective
            opposed_names.append(name)
        else:
            neutral += effective

    directional = aligned + opposed
    agreement = aligned / directional if directional > 0 else 0.0
    conflict = opposed / directional if directional > 0 else 0.0

    return {
        "agreement": round(max(0.0, min(1.0, agreement)), 3),
        "conflict": round(max(0.0, min(1.0, conflict)), 3),
        "aligned_weight": round(aligned, 4),
        "opposed_weight": round(opposed, 4),
        "neutral_weight": round(neutral, 4),
        "aligned_signals": aligned_names,
        "opposed_signals": opposed_names,
        "missing_signals": missing_names,
    }


def catalyst_context(snapshot: Dict[str, Any] | None) -> Dict[str, Any]:
    raw = snapshot or {}
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        raw = raw["data"]

    earnings_keys = (
        "earnings_catalyst_risk",
        "earnings_upcoming_within_8h",
        "earnings_upcoming_events",
    )
    macro_keys = (
        "macro_high_impact",
        "high_impact_macro_event",
        "macro_event_risk",
    )

    earnings_available = any(k in raw for k in earnings_keys)
    macro_available = any(k in raw for k in macro_keys)

    earnings_active = (
        _as_bool(raw.get("earnings_catalyst_risk"))
        or _as_float(raw.get("earnings_upcoming_within_8h")) > 0
        or _as_float(raw.get("earnings_upcoming_events")) > 0
    ) if earnings_available else False

    macro_active = any(_as_bool(raw.get(k)) for k in macro_keys) if macro_available else False

    if macro_active:
        status = "HIGH_IMPACT_MACRO"
    elif earnings_active:
        status = "EARNINGS_CATALYST"
    elif earnings_available or macro_available:
        status = "CLEAR"
    else:
        status = "UNAVAILABLE"

    return {
        "status": status,
        "earnings_active": bool(earnings_active),
        "macro_active": bool(macro_active),
        "earnings_context_available": bool(earnings_available),
        "macro_context_available": bool(macro_available),
        "note": (
            "Catalyst context never overrides the validated confidence/regime gate."
            if status != "UNAVAILABLE"
            else "No explicit live catalyst-risk fields were present in the snapshot."
        ),
    }


def build_accuracy_assessment(forecast: Any, snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Build a selective accuracy gate around the frozen Phase 21 forecast.

    Historical Phase 21 validation supports selectivity, especially TREND +
    confidence >=65, rather than rewriting the underlying forecast weights.
    """
    direction = str(_get(forecast, "direction", "NEUTRAL") or "NEUTRAL").upper()
    confidence = _as_float(_get(forecast, "confidence", 0.0))
    regime = str(_get(forecast, "regime", "UNKNOWN") or "UNKNOWN").upper()
    bullish = _as_float(_get(forecast, "bullish_probability", 50.0), 50.0)
    bearish = _as_float(_get(forecast, "bearish_probability", 50.0), 50.0)
    probability_gap = abs(bullish - bearish)

    alignment = evidence_alignment(forecast)
    catalyst = catalyst_context(snapshot)
    agreement = float(alignment["agreement"])
    conflict = float(alignment["conflict"])

    reasons: List[str] = []
    warnings: List[str] = []

    if regime == "TREND":
        reasons.append("TREND regime: historically the strongest broad directional regime in Phase 21.")
    else:
        warnings.append(f"{regime} regime is outside the primary validated accuracy gate.")

    if confidence >= 70.0:
        reasons.append("Confidence >=70%: strongest Phase 21 confidence band.")
    elif confidence >= 65.0:
        reasons.append("Confidence >=65%: inside the validated TREND+65 gate.")
    elif confidence >= 60.0:
        warnings.append("Confidence 60-64.9%: secondary/watch zone, not the primary high-accuracy gate.")
    else:
        warnings.append("Confidence <60%: low-selectivity zone.")

    if agreement >= 0.65:
        reasons.append(f"Evidence agreement is strong ({agreement:.0%}).")
    elif agreement >= 0.55:
        reasons.append(f"Evidence agreement is acceptable ({agreement:.0%}).")
    else:
        warnings.append(f"Evidence agreement is weak ({agreement:.0%}).")

    if conflict > 0.35:
        warnings.append(f"Evidence conflict is elevated ({conflict:.0%}).")
    elif conflict <= 0.25:
        reasons.append(f"Evidence conflict is contained ({conflict:.0%}).")

    # Accuracy-first grading. Probability gap is displayed but intentionally
    # not used as a primary gate because Phase 21 diagnostics showed that a
    # large probability gap alone was not a robust accuracy filter.
    if regime != "TREND" or confidence < 60.0:
        grade = "NO_TRADE"
        research_eligible = False
    elif confidence >= 70.0 and agreement >= 0.65 and conflict <= 0.25:
        grade = "A++"
        research_eligible = True
    elif confidence >= 65.0 and agreement >= 0.55 and conflict <= 0.35:
        grade = "A+"
        research_eligible = True
    elif confidence >= 60.0 and agreement >= 0.60 and conflict <= 0.30:
        grade = "A"
        research_eligible = False
    else:
        grade = "WATCH"
        research_eligible = False

    if catalyst["status"] == "HIGH_IMPACT_MACRO":
        warnings.append("High-impact macro context active: preserve the gate but treat timing as elevated risk.")
    elif catalyst["status"] == "EARNINGS_CATALYST":
        reasons.append("Earnings catalyst context is active; Phase 21 catalyst days were stronger than ordinary days overall.")

    confidence_band = (
        "70%+" if confidence >= 70.0
        else "65-69.9%" if confidence >= 65.0
        else "60-64.9%" if confidence >= 60.0
        else "<60%"
    )

    return {
        "ok": True,
        "phase": "PHASE 24",
        "module": "Accuracy Engine",
        "direction": direction,
        "setup_grade": grade,
        "research_eligible": research_eligible,
        "regime_policy": {
            "regime": regime,
            "primary_validated_regime": "TREND",
            "pass": regime == "TREND",
        },
        "confidence_gate": {
            "confidence": round(confidence, 1),
            "band": confidence_band,
            "primary_threshold": 65.0,
            "high_threshold": 70.0,
            "pass": confidence >= 65.0,
        },
        "probability": {
            "bullish": round(bullish, 1),
            "bearish": round(bearish, 1),
            "gap": round(probability_gap, 1),
            "note": "Probability gap is context, not a standalone accuracy gate.",
        },
        "evidence": alignment,
        "catalyst": catalyst,
        "reasons": reasons,
        "warnings": warnings,
        "frozen_core": {
            "forecast_direction_changed": False,
            "forecast_probability_changed": False,
            "forecast_confidence_changed": False,
            "forecast_weights_changed": False,
        },
    }
