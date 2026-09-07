# PHASE25_CHART_CONFLUENCE_V1
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _text(value).lower() in {"1", "true", "yes", "y", "on", "detected", "present", "valid", "confirmed"}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _items(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        # A single structured observation should be treated as one item.
        return [value]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [value]


def _contains_direction(value: Any, direction: str) -> bool:
    """Best-effort direction alignment without fabricating chart evidence."""
    direction = _upper(direction)
    if not direction:
        return False

    if isinstance(value, dict):
        candidates = [
            value.get("direction"), value.get("bias"), value.get("side"),
            value.get("reaction"), value.get("confirmation"), value.get("trend"),
        ]
        joined = " ".join(_text(x) for x in candidates).upper()
    else:
        joined = _text(value).upper()

    if direction == "BULLISH":
        return any(k in joined for k in ("BULL", "LONG", "DEMAND", "RECLAIM", "SELL-SIDE", "SELL SIDE", "SSL"))
    if direction == "BEARISH":
        return any(k in joined for k in ("BEAR", "SHORT", "SUPPLY", "REJECT", "BUY-SIDE", "BUY SIDE", "BSL"))
    return False


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "none", "n/a", "na", "unknown", "not visible", "not detected", "false"}
    return True


def _first_present(chart: Dict[str, Any], *keys: str):
    for key in keys:
        if key in chart and _present(chart.get(key)):
            return chart.get(key)
    return None


def _feature_state(chart: Dict[str, Any], keys: Tuple[str, ...], direction: str) -> Dict[str, Any]:
    raw = _first_present(chart, *keys)
    present = _present(raw)
    aligned = False
    if present:
        if isinstance(raw, bool):
            # A boolean means "detected", not directional. It can count as present
            # but cannot be promoted to aligned without a directional field.
            aligned = False
        else:
            aligned = any(_contains_direction(item, direction) for item in _items(raw))
    return {"present": present, "aligned": aligned, "raw": raw}


def _liquidity_state(chart: Dict[str, Any], direction: str) -> Dict[str, Any]:
    raw = _first_present(
        chart,
        "liquidity_sweeps", "liquidity_sweep", "sweep_reclaim", "sweep_rejection",
        "liquidity_event", "liquidity_levels",
    )
    present = _present(raw)
    aligned = False
    if present:
        direction = _upper(direction)
        for item in _items(raw):
            txt = jsonish(item)
            if direction == "BULLISH":
                # Bullish high-quality execution typically follows a sell-side sweep
                # and reclaim / bullish reaction.
                if any(k in txt for k in ("SELL-SIDE", "SELL SIDE", "SSL", "LOW SWEEP", "SWEPT LOW")) and any(k in txt for k in ("RECLAIM", "BULL", "LONG", "REVERS")):
                    aligned = True
                    break
                if _contains_direction(item, direction):
                    aligned = True
                    break
            elif direction == "BEARISH":
                # Bearish high-quality execution typically follows a buy-side sweep
                # and rejection / bearish reaction.
                if any(k in txt for k in ("BUY-SIDE", "BUY SIDE", "BSL", "HIGH SWEEP", "SWEPT HIGH")) and any(k in txt for k in ("REJECT", "BEAR", "SHORT", "REVERS")):
                    aligned = True
                    break
                if _contains_direction(item, direction):
                    aligned = True
                    break
    return {"present": present, "aligned": aligned, "raw": raw}


def jsonish(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            parts.append(f"{k}:{v}")
        return " ".join(parts).upper()
    return _text(value).upper()


def chart_confluence_features(chart_analysis: Dict[str, Any], fia_direction: str) -> Dict[str, Any]:
    chart = chart_analysis or {}
    fia_direction = _upper(fia_direction)
    chart_direction = _upper(chart.get("direction"))

    htf = _feature_state(chart, ("htf_poi", "higher_timeframe_poi", "poi", "htf_zone"), fia_direction)
    ob = _feature_state(chart, ("order_blocks", "order_block", "ob"), fia_direction)
    fvg = _feature_state(chart, ("fair_value_gaps", "fair_value_gap", "fvg", "fvgs"), fia_direction)
    liquidity = _liquidity_state(chart, fia_direction)
    smt = _feature_state(chart, ("smt", "smt_divergence", "smt_confirmation"), fia_direction)
    session = _feature_state(chart, ("session_context", "session", "session_confirmation"), fia_direction)
    execution = _feature_state(chart, ("execution_confirmation", "lower_timeframe_confirmation", "ltf_confirmation", "entry_confirmation"), fia_direction)

    # For explicit structured booleans, allow a separate *_direction field to
    # establish alignment without inventing direction from the boolean itself.
    direction_fields = {
        "htf_poi": (htf, chart.get("htf_poi_direction")),
        "order_block": (ob, chart.get("order_block_direction")),
        "fvg": (fvg, chart.get("fvg_direction")),
        "liquidity": (liquidity, chart.get("liquidity_direction")),
        "smt": (smt, chart.get("smt_direction")),
        "session": (session, chart.get("session_direction")),
        "execution": (execution, chart.get("execution_direction")),
    }
    for _, (state, value) in direction_fields.items():
        if state["present"] and _upper(value) == fia_direction:
            state["aligned"] = True

    return {
        "fia_direction": fia_direction,
        "chart_direction": chart_direction or "UNKNOWN",
        "direction_match": chart_direction == fia_direction if chart_direction in {"BULLISH", "BEARISH"} else None,
        "htf_poi": htf,
        "order_block": ob,
        "fair_value_gap": fvg,
        "liquidity_sweep_reclaim": liquidity,
        "smt": smt,
        "session_context": session,
        "execution_confirmation": execution,
    }


def build_confluence_assessment(
    forecast: Any,
    accuracy_assessment: Dict[str, Any],
    chart_analysis: Dict[str, Any],
    snapshot: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Combine frozen FIA research with explicit chart confluence evidence.

    Phase 25 is a FILTER / CLASSIFICATION layer only. It does not alter the
    Phase 21 forecast direction, probabilities, confidence, signal weights, or
    broker/execution behavior.
    """
    direction = _upper(_get(forecast, "direction", ""))
    features = chart_confluence_features(chart_analysis or {}, direction)
    phase24_grade = _upper((accuracy_assessment or {}).get("setup_grade", "NO_TRADE"))
    phase24_eligible = bool((accuracy_assessment or {}).get("research_eligible", False))

    weights = {
        "direction_match": 20,
        "htf_poi": 15,
        "order_block": 15,
        "fair_value_gap": 10,
        "liquidity_sweep_reclaim": 20,
        "smt": 10,
        "session_context": 5,
        "execution_confirmation": 5,
    }

    score = 0.0
    observed_weight = 0.0
    aligned_weight = 0.0
    reasons: List[str] = []
    warnings: List[str] = []
    missing: List[str] = []

    dm = features.get("direction_match")
    if dm is True:
        score += weights["direction_match"]
        observed_weight += weights["direction_match"]
        aligned_weight += weights["direction_match"]
        reasons.append("Chart direction agrees with FIA direction.")
    elif dm is False:
        observed_weight += weights["direction_match"]
        warnings.append("Chart direction conflicts with FIA direction.")
    else:
        missing.append("chart_direction")

    feature_keys = [
        "htf_poi", "order_block", "fair_value_gap", "liquidity_sweep_reclaim",
        "smt", "session_context", "execution_confirmation",
    ]
    pretty = {
        "htf_poi": "HTF POI",
        "order_block": "Order Block",
        "fair_value_gap": "FVG",
        "liquidity_sweep_reclaim": "Liquidity sweep/reclaim",
        "smt": "SMT",
        "session_context": "Session context",
        "execution_confirmation": "Execution confirmation",
    }

    for key in feature_keys:
        state = features[key]
        w = weights[key]
        if not state["present"]:
            missing.append(key)
            continue
        observed_weight += w
        if state["aligned"]:
            score += w
            aligned_weight += w
            reasons.append(f"{pretty[key]} aligns with FIA direction.")
        else:
            warnings.append(f"{pretty[key]} is present but not directionally confirmed.")

    completeness = observed_weight / sum(weights.values()) if weights else 0.0
    alignment = aligned_weight / observed_weight if observed_weight > 0 else 0.0

    # Hard safety gates first: Phase24 selectivity and chart/FIA direction.
    if dm is False:
        final_grade = "NO_TRADE"
        research_eligible = False
    elif phase24_grade in {"NO_TRADE", "WATCH"} or not phase24_eligible:
        final_grade = "NO_TRADE" if phase24_grade == "NO_TRADE" else "WATCH"
        research_eligible = False
    else:
        # A++ requires the most important execution context: direction match,
        # liquidity sweep/reclaim and enough independently observed confluence.
        liquidity_ok = bool(features["liquidity_sweep_reclaim"]["aligned"])
        core_count = sum(
            1 for k in ("htf_poi", "order_block", "fair_value_gap", "smt")
            if features[k]["aligned"]
        )
        if score >= 85 and completeness >= 0.80 and liquidity_ok and core_count >= 3:
            final_grade = "A++"
            research_eligible = True
        elif score >= 70 and completeness >= 0.65 and liquidity_ok and core_count >= 2:
            final_grade = "A+"
            research_eligible = True
        elif score >= 55 and completeness >= 0.55:
            final_grade = "A"
            research_eligible = False
        else:
            final_grade = "WATCH"
            research_eligible = False

    if phase24_grade == "A++":
        reasons.append("Phase 24 accuracy gate is A++.")
    elif phase24_grade == "A+":
        reasons.append("Phase 24 accuracy gate is A+.")
    else:
        warnings.append(f"Phase 24 gate is {phase24_grade}; chart confluence cannot override a weak FIA gate.")

    return {
        "ok": True,
        "phase": "PHASE 25",
        "module": "A++ Chart Confluence",
        "setup_grade": final_grade,
        "research_eligible": research_eligible,
        "confluence_score": round(score, 1),
        "confluence_completeness": round(completeness, 3),
        "confluence_alignment": round(alignment, 3),
        "phase24_setup_grade": phase24_grade,
        "phase24_research_eligible": phase24_eligible,
        "features": features,
        "reasons": reasons,
        "warnings": warnings,
        "missing_evidence": missing,
        "grading_policy": {
            "A++": "Phase24 A+/A++ + score>=85 + completeness>=80% + aligned liquidity sweep/reclaim + >=3 aligned core chart features",
            "A+": "Phase24 eligible + score>=70 + completeness>=65% + aligned liquidity sweep/reclaim + >=2 aligned core chart features",
            "A": "score>=55 + completeness>=55%; research watch only",
            "WATCH": "insufficient confirmed confluence",
            "NO_TRADE": "Phase24 rejection or chart/FIA directional conflict",
        },
        "frozen_core": {
            "forecast_direction_changed": False,
            "forecast_probability_changed": False,
            "forecast_confidence_changed": False,
            "forecast_weights_changed": False,
            "broker_execution_added": False,
        },
        "note": "Phase 25 classifies research confluence. It does not claim historical accuracy improvement until A/A+/A++ labels are forward-recorded and validated in Phase 26.",
    }
