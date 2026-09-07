from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


FEATURE_PATTERNS = {
    "htf_poi": (r"\bpoi\b", r"supply", r"demand", r"high[ -]?timeframe", r"\bhtf\b"),
    "order_block": (r"order block", r"\bob\b"),
    "fair_value_gap": (r"fair value gap", r"\bfvg\b", r"imbalance"),
    "liquidity_sweep": (r"liquidity", r"sweep", r"reclaim", r"buy[ -]?side", r"sell[ -]?side", r"\bbsl\b", r"\bssl\b"),
    "smt": (r"\bsmt\b", r"divergence"),
    "structure_shift": (r"\bchoch\b", r"change of character", r"\bmss\b", r"market structure shift", r"\bbos\b", r"break of structure"),
    "displacement": (r"displacement", r"impulsive", r"impulse"),
    "execution_confirmation": (r"confirmation", r"entry trigger", r"1m", r"one minute", r"5m", r"five minute"),
}


def _direction(value: Any) -> str:
    x = str(value or "NEUTRAL").strip().upper()
    return x if x in {"BULLISH", "BEARISH", "NEUTRAL"} else "NEUTRAL"


def _obj_value(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _truthy_feature(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        if "detected" in value:
            return bool(value.get("detected"))
        return bool(value)
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    return str(value).strip().lower() not in {"", "none", "false", "unknown", "not detected", "n/a"}


def _vision_features(vision: Dict[str, Any]) -> Dict[str, bool]:
    return {
        "htf_poi": _truthy_feature(vision.get("htf_poi")),
        "order_block": _truthy_feature(vision.get("order_blocks")),
        "fair_value_gap": _truthy_feature(vision.get("fair_value_gaps")),
        "liquidity_sweep": _truthy_feature(vision.get("liquidity_sweep")),
        "smt": _truthy_feature(vision.get("smt")),
        "structure_shift": _truthy_feature(vision.get("structure_shift")),
        "displacement": _truthy_feature(vision.get("displacement")),
        "execution_confirmation": _truthy_feature(vision.get("execution_confirmation")),
    }


def _user_features(user: Dict[str, Any]) -> Dict[str, bool]:
    explicit = user.get("features") if isinstance(user.get("features"), dict) else {}
    text = " ".join(
        str(user.get(k) or "") for k in ("reasoning", "levels", "notes", "thesis")
    ).lower()
    result: Dict[str, bool] = {}
    for feature, patterns in FEATURE_PATTERNS.items():
        if feature in explicit:
            result[feature] = bool(explicit.get(feature))
            continue
        result[feature] = any(re.search(p, text, flags=re.I) for p in patterns)
    return result


def _agreement(a: str, b: str) -> str:
    if "NEUTRAL" in {a, b}:
        return "PARTIAL" if a == b else "UNRESOLVED"
    return "ALIGNED" if a == b else "CONFLICT"


def _matched_features(user_features: Dict[str, bool], vision_features: Dict[str, bool]) -> Tuple[List[str], List[str], List[str]]:
    confirmed, user_only, vision_only = [], [], []
    for key in sorted(set(user_features) | set(vision_features)):
        u = bool(user_features.get(key))
        v = bool(vision_features.get(key))
        if u and v:
            confirmed.append(key)
        elif u and not v:
            user_only.append(key)
        elif v and not u:
            vision_only.append(key)
    return confirmed, user_only, vision_only


def build_three_way_confluence(
    forecast: Any,
    user_analysis: Dict[str, Any],
    vision_analysis: Dict[str, Any],
    phase25_assessment: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compare FIA, user's plan and an independently generated Vision opinion.

    The vision leg must be produced without exposing FIA/user direction to the
    chart model. This layer does not change the frozen FIA forecast and does not
    claim a trading edge until out-of-sample validation supports it.
    """
    user_analysis = user_analysis or {}
    vision_analysis = vision_analysis or {}

    fia_direction = _direction(_obj_value(forecast, "direction", "NEUTRAL"))
    user_direction = _direction(user_analysis.get("direction"))
    vision_direction = _direction(vision_analysis.get("direction"))

    fia_user = _agreement(fia_direction, user_direction)
    fia_vision = _agreement(fia_direction, vision_direction)
    user_vision = _agreement(user_direction, vision_direction)

    all_directional = all(x in {"BULLISH", "BEARISH"} for x in (fia_direction, user_direction, vision_direction))
    all_same = all_directional and len({fia_direction, user_direction, vision_direction}) == 1
    any_conflict = "CONFLICT" in {fia_user, fia_vision, user_vision}

    u_features = _user_features(user_analysis)
    v_features = _vision_features(vision_analysis)
    confirmed, user_only, vision_only = _matched_features(u_features, v_features)

    # Evidence score is deliberately transparent and bounded. It is a research
    # confluence score, NOT a calibrated probability and NOT a historical edge claim.
    direction_score = 45 if all_same else (20 if not any_conflict else 0)
    feature_score = min(40, len(confirmed) * 8)
    clarity = float(vision_analysis.get("confidence") or 0.0)
    clarity_score = min(15.0, max(0.0, clarity) * 0.15)
    score = round(min(100.0, direction_score + feature_score + clarity_score), 1)

    phase25_grade = str((phase25_assessment or {}).get("setup_grade") or "UNVALIDATED").upper()
    conflicts: List[str] = []
    if fia_user == "CONFLICT":
        conflicts.append("User direction conflicts with FIA.")
    if fia_vision == "CONFLICT":
        conflicts.append("Independent Vision direction conflicts with FIA.")
    if user_vision == "CONFLICT":
        conflicts.append("User direction conflicts with Independent Vision.")
    if user_only:
        conflicts.append("Some user-claimed chart features were not independently confirmed by Vision.")

    if all_same and len(confirmed) >= 4 and clarity >= 70:
        candidate_grade = "A++"
    elif all_same and len(confirmed) >= 2 and clarity >= 55:
        candidate_grade = "A+"
    elif not any_conflict and len(confirmed) >= 1:
        candidate_grade = "A"
    else:
        candidate_grade = "WATCH" if not any_conflict else "NO_TRADE"

    # Safety: A/A+/A++ is a candidate research label unless OOS evidence proves
    # monotonic quality. We never convert this into a broker action.
    validation_gate = "OOS_VALIDATION_REQUIRED"
    research_hold = any_conflict or vision_direction == "NEUTRAL" or fia_direction == "NEUTRAL"

    return {
        "ok": True,
        "phase": "PHASE 31",
        "module": "FIA + USER + INDEPENDENT VISION THREE-WAY CONFLUENCE",
        "fia_direction": fia_direction,
        "user_direction": user_direction,
        "vision_direction": vision_direction,
        "pairwise": {
            "fia_vs_user": fia_user,
            "fia_vs_vision": fia_vision,
            "user_vs_vision": user_vision,
        },
        "three_way_alignment": "ALIGNED" if all_same else ("CONFLICT" if any_conflict else "MIXED"),
        "consensus_direction": fia_direction if all_same else "NONE",
        "independent_feature_check": {
            "user_claimed": [k for k, v in u_features.items() if v],
            "vision_detected": [k for k, v in v_features.items() if v],
            "confirmed_by_both": confirmed,
            "user_only_unconfirmed": user_only,
            "vision_only": vision_only,
        },
        "confluence_score": score,
        "candidate_setup_grade": candidate_grade,
        "phase25_grade": phase25_grade,
        "validation_gate": validation_gate,
        "research_hold": research_hold,
        "conflicts": conflicts,
        "independence": {
            "vision_saw_fia_direction": False,
            "vision_saw_user_direction": False,
            "vision_saw_user_reasoning": False,
            "comparison_happens_after_independent_vision": True,
        },
        "frozen_core": {
            "forecast_direction_changed": False,
            "forecast_probability_changed": False,
            "forecast_weights_changed": False,
            "broker_execution_added": False,
        },
        "research_only": True,
        "broker_execution": False,
        "note": "A/A+/A++ is a research candidate grade until untouched out-of-sample data proves that higher grades are monotonically more accurate.",
    }
