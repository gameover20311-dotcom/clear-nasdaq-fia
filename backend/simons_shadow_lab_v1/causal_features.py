"""Lock-time-only feature extraction for SIMONS SHADOW LAB V2 hybrid.

"Causal" here means temporal discipline: every feature is derived only from
information present in the immutable forecast lock. It does NOT claim a proven
causal relationship with future NQ returns.

V2 adds a structural anti-leakage barrier: feature code receives a guarded view
that raises if prediction-time logic attempts to access outcome/resolution data,
including through ``.get()``. This is stronger than relying on convention alone.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional

from .lab import _float
from .strict_contract import LockTimeRowView, validate_horizon_distribution

_SIGNAL_ALIASES = {
    "nq_structure": ("nq structure", "price structure"),
    "spx_confirmation": ("spx confirmation", "spx"),
    "dxy": ("dxy", "dollar"),
    "us10y": ("us10y", "10y", "yield"),
    "mega_cap_leadership": ("mega-cap leadership", "megacap leadership", "big tech"),
    "semiconductors": ("semiconductors", "semiconductor", "semis"),
    "participation": ("equal-weight participation", "breadth", "participation"),
    "news": ("news",),
    "macro_calendar": ("macro calendar", "macro"),
    "earnings_guidance": ("earnings/guidance", "earnings", "guidance"),
}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def canonical_signal_name(name: Any) -> Optional[str]:
    text = _norm(name)
    for canonical, aliases in _SIGNAL_ALIASES.items():
        if any(alias in text for alias in aliases):
            return canonical
    return None


def extract_lock_time_features(row: Mapping[str, Any], hours: int) -> Dict[str, Any]:
    """Extract features through the mechanical lock-time barrier only."""
    if hours not in (4, 8):
        raise ValueError("hours must be 4 or 8")
    view = row if isinstance(row, LockTimeRowView) else LockTimeRowView(row)
    base = view.get("base") or {}
    h = base.get(f"h{hours}") or {}
    other = base.get("h8" if hours == 4 else "h4") or {}

    # Validate real two-way probability distributions when present. Missing
    # distributions remain missing (fail-closed for any rule requiring them),
    # while malformed distributions are rejected loudly.
    dist = validate_horizon_distribution(base, hours)
    if dist.get("reason") not in {None, "missing_distribution"} and not dist.get("ok"):
        raise ValueError(f"invalid {hours}H distribution: {dist.get('reason')}")

    bull = _float(h.get("bullish_probability"))
    bear = _float(h.get("bearish_probability"))
    confidence = _float(h.get("confidence"))
    direction = str(h.get("direction") or base.get("direction") or "").upper()
    edge = abs((bull or 50.0) - (bear or 50.0)) if bull is not None and bear is not None else None

    scores: Dict[str, Optional[float]] = {key: None for key in _SIGNAL_ALIASES}
    freshness: Dict[str, Optional[str]] = {key: None for key in _SIGNAL_ALIASES}
    for raw in base.get("signals") or ():
        if not isinstance(raw, Mapping):
            continue
        key = canonical_signal_name(raw.get("name"))
        if key:
            scores[key] = _float(raw.get("score"))
            freshness[key] = str(raw.get("freshness") or "").upper() or None

    available = sum(1 for key, score in scores.items() if score is not None and freshness.get(key) not in {"MISSING", "STALE", "UNAVAILABLE"})
    missing = len(scores) - available
    target_sign = 1 if direction == "BULLISH" else -1 if direction == "BEARISH" else 0
    aligned = opposed = neutral = 0
    for score in scores.values():
        if score is None or abs(score) < 1e-12 or target_sign == 0:
            neutral += 1
        elif score * target_sign > 0:
            aligned += 1
        else:
            opposed += 1

    other_direction = str(other.get("direction") or "").upper()
    other_bull = _float(other.get("bullish_probability"))
    divergence = abs(bull - other_bull) if bull is not None and other_bull is not None else None
    source_status = base.get("source_status") or {}
    source_missing = sum(1 for value in source_status.values() if isinstance(value, str) and any(token in value.lower() for token in ("missing", "unavailable", "stale")))

    features: Dict[str, Any] = {
        "forecast_id": view.get("forecast_id"),
        "horizon_hours": hours,
        "fia_direction": direction,
        "bullish_probability": bull,
        "bearish_probability": bear,
        "confidence": confidence,
        "edge_points": edge,
        "regime": str(base.get("regime") or "UNKNOWN").upper(),
        "status": str(base.get("status") or "").upper(),
        "data_coverage": _float(base.get("data_coverage")),
        "intelligence_coverage": _float(base.get("intelligence_coverage")),
        "horizon_state": str(h.get("state") or "").upper() or None,
        "actionable": h.get("actionable"),
        "horizon_agreement": bool(direction and direction == other_direction),
        "other_horizon_direction": other_direction or None,
        "probability_divergence_points": divergence,
        "component_alignment_count": aligned,
        "component_opposition_count": opposed,
        "component_neutral_or_missing_count": neutral,
        "available_component_count": available,
        "missing_component_count": missing,
        "missing_component_ratio": (missing / len(scores)) if scores else None,
        "source_status_missing_or_stale_count": source_missing,
        "component_alignment_is_independent_evidence": False,
        "lock_time_barrier_enforced": True,
        "distribution_contract_ok": bool(dist.get("ok")),
    }
    for key, value in scores.items():
        features[f"signal_{key}_score"] = value
        features[f"signal_{key}_freshness"] = freshness.get(key)
    return features


def state_signature(features: Mapping[str, Any]) -> str:
    prob = _float(features.get("bullish_probability"))
    conf = _float(features.get("confidence"))
    edge = _float(features.get("edge_points"))
    prob_bucket = "P?" if prob is None else "P65+" if prob >= 65 else "P55-65" if prob >= 55 else "P<=35" if prob <= 35 else "P35-45" if prob <= 45 else "P45-55"
    conf_bucket = "C?" if conf is None else "C60+" if conf >= 60 else "C40-60" if conf >= 40 else "C20-40" if conf >= 20 else "C<20"
    edge_bucket = "E?" if edge is None else "E30+" if edge >= 30 else "E15-30" if edge >= 15 else "E5-15" if edge >= 5 else "E<5"
    align = int(features.get("component_alignment_count") or 0)
    align_bucket = "A6+" if align >= 6 else "A4-5" if align >= 4 else "A2-3" if align >= 2 else "A0-1"
    return "|".join([
        str(features.get("regime") or "UNKNOWN"),
        str(features.get("fia_direction") or "UNKNOWN"),
        prob_bucket, conf_bucket, edge_bucket, align_bucket,
        "AGREE" if features.get("horizon_agreement") else "DIVERGE",
    ])
