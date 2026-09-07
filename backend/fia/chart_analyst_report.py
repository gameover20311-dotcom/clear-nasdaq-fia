"""CLEAR NASDAQ — CHART ANALYST REPORT (assembly layer).

WHAT THIS IS
------------
A pure, side-effect-free assembly layer that turns three already-existing inputs

    1. the INDEPENDENT vision analysis  (fia.advanced_chart_intelligence)
    2. the user's own written analysis
    3. the REAL FIA backend state       (pre-move watch, forecast, snapshot)

into a single report whose top block a trader can read in 5-10 seconds.

WHY IT EXISTS
-------------
The vision leg and the three-way confluence leg were already good, but nothing
assembled them against the *real* 4H/8H pre-move state, regime, drivers,
catalyst risk and evidence quality. This module does only that assembly. It
adds no new model call, no new provider, and no new probability.

THE ONE RULE THIS MODULE ENFORCES
---------------------------------
Chart-derived claims and backend-verified facts are NEVER merged into a single
undifferentiated statement. Every emitted claim carries an explicit origin:

    origin="CHART"    -> read from the uploaded image by the vision model.
                         It is an opinion about pixels. It is NOT market truth.
    origin="BACKEND"  -> verified from live FIA provider evidence.

A vision model can hallucinate a level, a sweep or a session. It cannot be
allowed to state a live market fact. Therefore:

  * nothing under `verified_backend` may originate from the image, and
  * nothing under `chart_only` is ever presented as confirmed market data.

Missing, stale or degraded backend evidence stays missing here. It is never
silently promoted to NEUTRAL, and absence of a reading is never scored as
agreement.

NOT PROVIDED, DELIBERATELY
--------------------------
No win rate, no expectancy, no calibrated probability for the *setup*, and no
claim that a higher setup grade is more accurate. Grades remain research
candidates until Forward-OOS evidence says otherwise.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CHART = "CHART"
BACKEND = "BACKEND"

DIRECTIONS = {"BULLISH", "BEARISH", "NEUTRAL"}
UNKNOWN = "UNKNOWN"

# A chart feature is only reported as present when the vision model set
# detected=true (or returned a non-empty list). Everything else is reported
# as NOT_CONFIRMED rather than as absence-of-feature, because "the model did
# not see it" and "it is not there" are different statements.
NOT_CONFIRMED = "NOT_CONFIRMED"
DETECTED = "DETECTED"

_FEATURE_KEYS = (
    ("htf_poi", "HTF POI / supply-demand zone"),
    ("order_blocks", "Order block"),
    ("fair_value_gaps", "Fair value gap / imbalance"),
    ("session_liquidity", "Session high / low"),
    ("liquidity_sweep", "Liquidity sweep"),
    ("smt", "SMT divergence"),
    ("structure_shift", "Market structure shift (CHoCH / MSS / BOS)"),
    ("displacement", "Displacement"),
    ("execution_confirmation", "Execution confirmation"),
)


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _obj(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _lst(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _direction(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if text in DIRECTIONS else UNKNOWN


def _pct(value: Any) -> Optional[float]:
    """Strict percentage reader. Booleans and blanks are not numbers."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= number <= 100.0:
        return None
    return round(number, 2)


def _feature_state(raw: Any) -> str:
    """DETECTED only on an explicit positive. Never infer from absence."""
    if isinstance(raw, dict):
        return DETECTED if bool(raw.get("detected")) else NOT_CONFIRMED
    if isinstance(raw, (list, tuple, set)):
        return DETECTED if len(raw) > 0 else NOT_CONFIRMED
    if isinstance(raw, bool):
        return DETECTED if raw else NOT_CONFIRMED
    return NOT_CONFIRMED


def _feature_note(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("note") or "").strip()
    if isinstance(raw, (list, tuple)) and raw:
        first = raw[0]
        if isinstance(first, dict):
            return str(first.get("note") or first.get("type") or "").strip()
        return str(first).strip()
    return ""


# --------------------------------------------------------------------------- #
# A · CHART-ONLY  (opinion about pixels)
# --------------------------------------------------------------------------- #
def build_chart_only(vision: Dict[str, Any]) -> Dict[str, Any]:
    vision = _obj(vision)
    direction = _direction(vision.get("direction"))
    bullish = _pct(vision.get("bullish_probability"))
    confidence = _pct(vision.get("confidence"))

    features: List[Dict[str, Any]] = []
    for key, label in _FEATURE_KEYS:
        raw = vision.get(key)
        state = _feature_state(raw)
        features.append(
            {
                "key": key,
                "label": label,
                "state": state,
                "note": _feature_note(raw) if state == DETECTED else "",
                "origin": CHART,
            }
        )

    detected = [f["key"] for f in features if f["state"] == DETECTED]
    unconfirmed = [f["key"] for f in features if f["state"] == NOT_CONFIRMED]

    # Chart clarity gates whether the image can carry a directional read at all.
    if direction == UNKNOWN or confidence is None:
        readable = "UNCLEAR"
    elif confidence < 25.0:
        readable = "LOW_CLARITY"
    else:
        readable = "READABLE"

    return {
        "origin": CHART,
        "what_this_is": (
            "The vision model's reading of the uploaded image only. "
            "It is not market data and has not been verified against any provider."
        ),
        "instrument_visible": vision.get("instrument") or UNKNOWN,
        "timeframes_visible": _lst(vision.get("timeframes_visible")) or [],
        "direction": direction,
        "bullish_probability": bullish,
        "bearish_probability": _pct(vision.get("bearish_probability")),
        "chart_clarity_confidence": confidence,
        "readability": readable,
        "features": features,
        "features_detected": detected,
        "features_not_confirmed": unconfirmed,
        "supporting_observations": _lst(vision.get("supporting_observations")),
        "conflicting_observations": _lst(vision.get("conflicting_observations")),
        "missing_evidence": _lst(vision.get("missing_evidence")),
        "visible_invalidation": str(vision.get("invalidation") or "").strip() or UNKNOWN,
        "thesis": str(vision.get("thesis") or "").strip(),
        "provider": vision.get("provider") or UNKNOWN,
        "model": vision.get("model") or UNKNOWN,
        "caveat": (
            "Levels, sessions and ICT/SMC labels here are read from pixels. "
            "Anything the model could not support is reported NOT_CONFIRMED "
            "rather than assumed absent."
        ),
    }


# --------------------------------------------------------------------------- #
# B · VERIFIED BACKEND  (real FIA evidence)
# --------------------------------------------------------------------------- #
def build_verified_backend(
    premove: Optional[Dict[str, Any]],
    forecast: Optional[Dict[str, Any]] = None,
    snapshot: Optional[Dict[str, Any]] = None,
    cognitive: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    premove = _obj(premove)
    forecast = _obj(forecast)
    snapshot = _obj(snapshot)
    cognitive = _obj(cognitive)

    horizons = _obj(premove.get("horizons"))

    def horizon(name: str) -> Dict[str, Any]:
        h = _obj(horizons.get(name))
        if not h:
            return {
                "available": False,
                "state": "MISSING_DATA",
                "direction": UNKNOWN,
                "bullish_probability": None,
                "confidence": None,
                "reason": "pre-move horizon not present in this snapshot",
            }
        calibration = _obj(h.get("calibration"))
        return {
            "available": True,
            "state": str(h.get("state") or UNKNOWN).upper(),
            "direction": _direction(h.get("direction")),
            "bullish_probability": _pct(h.get("bullish_probability")),
            "bearish_probability": _pct(h.get("bearish_probability")),
            "confidence": _pct(h.get("confidence")),
            "raw_probability": _pct(h.get("raw_probability")),
            # The share of the published number contributed by the calibration
            # intercept alone. Surfaced because it is base rate, not evidence.
            "no_information_tilt_points": calibration.get("no_information_tilt_points"),
            "calibration_flips_direction": bool(h.get("calibration_flips_direction")),
            "direction_basis": h.get("direction_basis"),
        }

    h8 = horizon("8h")
    h4 = horizon("4h")

    quality = _obj(premove.get("evidence_quality"))
    catalyst = _obj(premove.get("catalyst_risk"))

    drivers_raw = _lst(_obj(horizons.get("8h")).get("drivers"))
    drivers = [
        {
            "name": _obj(d).get("name"),
            "score": _obj(d).get("score"),
            "effective_weight": _obj(d).get("effective_weight"),
            "freshness": _obj(d).get("freshness"),
            "origin": BACKEND,
        }
        for d in drivers_raw
    ]
    drivers.sort(key=lambda d: abs(float(d.get("effective_weight") or 0.0)), reverse=True)

    critic = _obj(cognitive.get("critic"))
    hypotheses = _obj(cognitive.get("hypotheses"))

    market: Dict[str, Any] = {}
    for key in (
        "dxy_value",
        "us10y_value",
        "vix_value",
        "spx_confirmation",
        "semis",
        "breadth",
        "mega_cap",
        "nq_structure",
        "price",
    ):
        if key in snapshot:
            market[key] = snapshot.get(key)

    # Every source that did not report stays visible as missing.
    provider = _obj(snapshot.get("provider_health"))
    missing_sources = _lst(provider.get("missing_sources"))
    stale_sources = _lst(provider.get("stale_sources"))

    return {
        "origin": BACKEND,
        "what_this_is": (
            "Verified live FIA evidence. Nothing in this block comes from the "
            "uploaded image."
        ),
        "premove_state": str(premove.get("state") or UNKNOWN).upper(),
        "horizon_8h": h8,
        "horizon_4h": h4,
        "regime": premove.get("regime") or forecast.get("regime") or UNKNOWN,
        "catalyst_risk": {
            "level": str(catalyst.get("level") or UNKNOWN).upper(),
            "known": bool(catalyst.get("known")),
            "earnings_catalyst_risk": catalyst.get("earnings_catalyst_risk"),
            "macro_high_impact": catalyst.get("macro_high_impact"),
            "origin": BACKEND,
        },
        "evidence_quality": {
            "coverage": quality.get("coverage"),
            "grade": quality.get("grade"),
            "live_signal_count": quality.get("live_signal_count"),
            "total_signal_count": quality.get("total_signal_count"),
            "degraded": bool(quality.get("degraded")),
            "stale": bool(quality.get("stale")),
            "not_live": bool(quality.get("not_live")),
            "origin": BACKEND,
        },
        "dominant_drivers": drivers[:5],
        "invalidation": _lst(premove.get("invalidation")) or _lst(forecast.get("invalidation")),
        "reasoning_layers": {
            "bull_strength": _obj(hypotheses.get("bullish_hypothesis")).get("strength"),
            "bear_strength": _obj(hypotheses.get("bearish_hypothesis")).get("strength"),
            "dominant_hypothesis": hypotheses.get("dominant_hypothesis"),
            "critic_severity": critic.get("severity"),
            "critic_objections": _lst(critic.get("objections")),
            "critic_hard_hold": critic.get("hard_hold"),
            "same_model_agreement_is_independent_evidence": False,
            "origin": BACKEND,
        },
        "market_context": market,
        "missing_sources": missing_sources,
        "stale_sources": stale_sources,
        "measured_performance": _obj(premove.get("measured_performance_disclosure")),
    }


# --------------------------------------------------------------------------- #
# agreement between the two independent reads
# --------------------------------------------------------------------------- #
def _agreement(chart: Dict[str, Any], backend: Dict[str, Any]) -> Dict[str, Any]:
    chart_dir = chart.get("direction")
    h8 = _obj(backend.get("horizon_8h"))
    h4 = _obj(backend.get("horizon_4h"))
    fia_dir = h8.get("direction")
    fia_state = str(h8.get("state") or "").upper()

    reasons: List[str] = []

    # Insufficient data dominates every other verdict. We never let an
    # unreadable chart or a degraded backend masquerade as agreement.
    if chart.get("readability") == "UNCLEAR" or chart_dir == UNKNOWN:
        reasons.append("Chart direction could not be read from the image.")
        verdict = "INSUFFICIENT_DATA"
    elif not h8.get("available"):
        reasons.append("No 8H pre-move reading is available from the backend.")
        verdict = "INSUFFICIENT_DATA"
    elif fia_state in {"NO_EDGE", "DEGRADED", "STALE", "MISSING_DATA"}:
        reasons.append(
            "FIA is not making a directional claim at 8H (state %s), so the "
            "chart read cannot be confirmed or contradicted." % fia_state
        )
        verdict = "INSUFFICIENT_DATA"
    elif fia_dir == UNKNOWN or fia_dir == "NEUTRAL":
        reasons.append("FIA 8H direction is not directional.")
        verdict = "INSUFFICIENT_DATA"
    elif chart_dir == "NEUTRAL":
        reasons.append("Chart read is neutral; no directional comparison is possible.")
        verdict = "INSUFFICIENT_DATA"
    elif chart_dir == fia_dir:
        reasons.append("Chart read and FIA 8H agree on %s." % fia_dir)
        h4_dir = h4.get("direction")
        if h4.get("available") and h4_dir in {"BULLISH", "BEARISH"} and h4_dir != chart_dir:
            reasons.append("4H disagrees with 8H, so agreement is partial across horizons.")
            verdict = "PARTIAL"
        else:
            verdict = "CONFIRMS"
    else:
        reasons.append("Chart read is %s while FIA 8H is %s." % (chart_dir, fia_dir))
        verdict = "CONFLICTS"

    # A confirmed direction on degraded evidence is still weakened, but it is
    # downgraded rather than discarded, and the reason is always stated.
    quality = _obj(backend.get("evidence_quality"))
    if verdict == "CONFIRMS" and (quality.get("degraded") or quality.get("stale")):
        verdict = "PARTIAL"
        reasons.append("Backend evidence is degraded or stale, so agreement is downgraded.")

    return {
        "verdict": verdict,
        "chart_direction": chart_dir,
        "fia_8h_direction": fia_dir,
        "fia_4h_direction": h4.get("direction"),
        "fia_8h_state": fia_state or UNKNOWN,
        "reasons": reasons,
        "note": (
            "Agreement is a present-time comparison between two independent "
            "reads. It does not establish which one is correct; only a resolved "
            "Forward-OOS outcome can do that."
        ),
    }


# --------------------------------------------------------------------------- #
# setup quality — descriptive only, never a probability
# --------------------------------------------------------------------------- #
def _setup_quality(
    chart: Dict[str, Any],
    backend: Dict[str, Any],
    agreement: Dict[str, Any],
) -> Dict[str, Any]:
    verdict = agreement.get("verdict")
    detected = len(chart.get("features_detected") or [])
    clarity = chart.get("chart_clarity_confidence") or 0.0
    quality = _obj(backend.get("evidence_quality"))
    degraded = bool(quality.get("degraded") or quality.get("stale") or quality.get("not_live"))

    blockers: List[str] = []
    if verdict == "INSUFFICIENT_DATA":
        blockers.append("Directional comparison is not possible.")
    if verdict == "CONFLICTS":
        blockers.append("Chart read conflicts with FIA.")
    if degraded:
        blockers.append("Backend evidence is degraded, stale or not live.")
    if _obj(backend.get("reasoning_layers")).get("critic_hard_hold"):
        blockers.append("Disconfirming Critic raised a hard hold.")

    if verdict == "INSUFFICIENT_DATA":
        grade = "NOT_GRADED"
    elif verdict == "CONFLICTS":
        grade = "NO_SETUP"
    elif blockers:
        grade = "WATCH"
    elif verdict == "CONFIRMS" and detected >= 4 and clarity >= 70:
        grade = "STRONG_CANDIDATE"
    elif verdict == "CONFIRMS" and detected >= 2 and clarity >= 55:
        grade = "CANDIDATE"
    elif verdict in {"CONFIRMS", "PARTIAL"}:
        grade = "WEAK_CANDIDATE"
    else:
        grade = "WATCH"

    return {
        "grade": grade,
        "basis": {
            "agreement": verdict,
            "chart_features_detected": detected,
            "chart_clarity_confidence": chart.get("chart_clarity_confidence"),
            "backend_evidence_degraded": degraded,
        },
        "blockers": blockers,
        "is_probability": False,
        "is_win_rate": False,
        "validation_gate": "OOS_VALIDATION_REQUIRED",
        "note": (
            "A descriptive research label built from chart clarity, feature "
            "count and agreement. It is not a probability, not a win rate, and "
            "carries no evidence that higher grades resolve more accurately. "
            "Measured performance shows no demonstrated edge."
        ),
    }


# --------------------------------------------------------------------------- #
# key reasons — max 3, every one tagged with its origin
# --------------------------------------------------------------------------- #
def _key_reasons(
    chart: Dict[str, Any],
    backend: Dict[str, Any],
    agreement: Dict[str, Any],
) -> List[Dict[str, str]]:
    reasons: List[Dict[str, str]] = []

    drivers = backend.get("dominant_drivers") or []
    if drivers:
        top = drivers[0]
        try:
            score = float(top.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        direction_word = "supports" if score > 0 else ("opposes" if score < 0 else "is flat for")
        h8_dir = _obj(backend.get("horizon_8h")).get("direction")
        conflict = (score < 0 and h8_dir == "BULLISH") or (score > 0 and h8_dir == "BEARISH")
        text = "%s is the heaviest driver (weight %s) and %s the published 8H direction." % (
            top.get("name"),
            top.get("effective_weight"),
            direction_word,
        )
        if conflict:
            text += " The strongest driver argues against the published call."
        reasons.append({"origin": BACKEND, "text": text})

    detected = chart.get("features_detected") or []
    if detected:
        labels = {k: lbl for k, lbl in _FEATURE_KEYS}
        named = ", ".join(labels.get(k, k) for k in detected[:3])
        reasons.append(
            {
                "origin": CHART,
                "text": "Visible in the image: %s." % named,
            }
        )
    else:
        reasons.append(
            {
                "origin": CHART,
                "text": "No chart structure feature could be confirmed from the image.",
            }
        )

    quality = _obj(backend.get("evidence_quality"))
    missing = backend.get("missing_sources") or []
    if missing or quality.get("degraded"):
        reasons.append(
            {
                "origin": BACKEND,
                "text": "Backend evidence is incomplete: %s missing. Coverage %s."
                % (", ".join(str(m) for m in missing) or "some sources", quality.get("coverage")),
            }
        )
    else:
        h8 = _obj(backend.get("horizon_8h"))
        tilt = h8.get("no_information_tilt_points")
        if tilt is not None:
            reasons.append(
                {
                    "origin": BACKEND,
                    "text": "Published 8H is %s%% from a raw %s%%; the calibration "
                    "intercept alone contributes %s points of unconditional base rate."
                    % (h8.get("bullish_probability"), h8.get("raw_probability"), tilt),
                }
            )

    return reasons[:3]


# --------------------------------------------------------------------------- #
# user comparison — FIA must not simply agree with the user
# --------------------------------------------------------------------------- #
def build_user_comparison(
    user_analysis: Dict[str, Any],
    chart: Dict[str, Any],
    backend: Dict[str, Any],
    three_way: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    user_analysis = _obj(user_analysis)
    three_way = _obj(three_way)

    user_dir = _direction(user_analysis.get("direction"))
    chart_dir = chart.get("direction")
    fia_dir = _obj(backend.get("horizon_8h")).get("direction")
    fia_state = str(_obj(backend.get("horizon_8h")).get("state") or "").upper()

    feature_check = _obj(three_way.get("independent_feature_check"))
    user_only = _lst(feature_check.get("user_only_unconfirmed"))
    confirmed_both = _lst(feature_check.get("confirmed_by_both"))

    reasons: List[str] = []

    if user_dir == UNKNOWN:
        verdict = "INSUFFICIENT_EVIDENCE"
        reasons.append("No user direction was provided.")
    elif fia_state in {"NO_EDGE", "DEGRADED", "STALE", "MISSING_DATA"} or fia_dir in {UNKNOWN, "NEUTRAL"}:
        verdict = "INSUFFICIENT_EVIDENCE"
        reasons.append(
            "FIA is not making a directional claim at 8H (state %s), so it can "
            "neither agree nor disagree." % (fia_state or UNKNOWN)
        )
    else:
        matches_fia = user_dir == fia_dir
        matches_chart = user_dir == chart_dir and chart_dir in {"BULLISH", "BEARISH"}
        if matches_fia and matches_chart:
            verdict = "AGREES"
            reasons.append("User, independent vision and FIA 8H all read %s." % user_dir)
        elif matches_fia and not matches_chart:
            verdict = "PARTIALLY_AGREES"
            reasons.append("FIA 8H agrees with the user, but the independent chart read does not.")
        elif matches_chart and not matches_fia:
            verdict = "PARTIALLY_AGREES"
            reasons.append("The chart read agrees with the user, but FIA 8H does not.")
        else:
            verdict = "DISAGREES"
            reasons.append("Neither FIA 8H nor the independent chart read supports the user direction.")

    if user_only:
        reasons.append(
            "Claimed but not confirmed by independent vision: %s." % ", ".join(str(x) for x in user_only)
        )
    if confirmed_both:
        reasons.append(
            "Independently confirmed: %s." % ", ".join(str(x) for x in confirmed_both)
        )

    return {
        "verdict": verdict,
        "user_direction": user_dir,
        "chart_direction": chart_dir,
        "fia_8h_direction": fia_dir,
        "confirmed_by_user_and_vision": confirmed_both,
        "user_claims_not_confirmed": user_only,
        "reasons": reasons,
        "policy": (
            "The vision leg never sees the user's direction or reasoning, and "
            "FIA never adopts the user's view. Agreement here is an observation, "
            "not a validation."
        ),
    }


# --------------------------------------------------------------------------- #
# top-level assembly
# --------------------------------------------------------------------------- #
def build_chart_analyst_report(
    vision: Dict[str, Any],
    user_analysis: Optional[Dict[str, Any]] = None,
    premove: Optional[Dict[str, Any]] = None,
    forecast: Optional[Dict[str, Any]] = None,
    snapshot: Optional[Dict[str, Any]] = None,
    cognitive: Optional[Dict[str, Any]] = None,
    three_way: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the full chart-analyst report. Pure: no I/O, no model calls."""
    chart = build_chart_only(vision)
    backend = build_verified_backend(premove, forecast, snapshot, cognitive)
    agreement = _agreement(chart, backend)
    quality = _setup_quality(chart, backend, agreement)
    reasons = _key_reasons(chart, backend, agreement)
    user_cmp = build_user_comparison(user_analysis or {}, chart, backend, three_way)

    h8 = _obj(backend.get("horizon_8h"))
    h4 = _obj(backend.get("horizon_4h"))

    # Invalidation is reported from both sides, never blended.
    invalidation = {
        "visible_in_chart": {
            "origin": CHART,
            "condition": chart.get("visible_invalidation"),
        },
        "verified_from_backend": {
            "origin": BACKEND,
            "conditions": backend.get("invalidation") or [],
        },
    }

    return {
        "ok": True,
        "module": "CLEAR NASDAQ — CHART ANALYST REPORT",
        "headline": {
            "chart_read": {
                "origin": CHART,
                "direction": chart.get("direction"),
                "readability": chart.get("readability"),
                "clarity_confidence": chart.get("chart_clarity_confidence"),
            },
            "fia_read": {
                "origin": BACKEND,
                "state": backend.get("premove_state"),
                "direction_8h": h8.get("direction"),
                "bullish_probability_8h": h8.get("bullish_probability"),
                "confidence_8h": h8.get("confidence"),
                "direction_4h": h4.get("direction"),
                "bullish_probability_4h": h4.get("bullish_probability"),
                "confidence_4h": h4.get("confidence"),
            },
            "agreement": agreement,
            "setup_quality": quality,
            "key_reasons": reasons,
            "invalidation": invalidation,
        },
        "chart_only": chart,
        "verified_backend": backend,
        "user_comparison": user_cmp,
        "three_way": three_way or None,
        "separation_policy": {
            "chart_claims_are_market_facts": False,
            "vision_may_state_live_market_data": False,
            "vision_saw_fia_direction": False,
            "vision_saw_user_direction": False,
            "missing_evidence_converted_to_neutral": False,
            "horizons_blended": False,
            "same_model_agreement_is_independent_evidence": False,
        },
        "research_only": True,
        "broker_execution": False,
        "note": (
            "Chart-derived observations and backend-verified evidence are kept "
            "in separate blocks and each claim is tagged with its origin. "
            "Nothing here is a trade instruction."
        ),
    }
