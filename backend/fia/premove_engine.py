# CLEAR NASDAQ — FIA Pre-Move Intelligence Layer
# Additive research layer. Does NOT overwrite the validated core FIA forecast.
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DEFAULT_HISTORY = Path(__file__).resolve().parents[1] / "fia_premove" / "data" / "premove_history.jsonl"
MAX_HISTORY_ROWS = int(os.getenv("FIA_PREMOVE_MAX_HISTORY", "2500"))

LEADING_SIGNAL_NAMES = {
    "SPX confirmation",
    "DXY",
    "US10Y",
    "Mega-cap leadership",
    "Semiconductors",
    "Breadth",
    "News",
    "Macro calendar",
    "Earnings/guidance",
}
PRICE_SIGNAL_NAMES = {"NQ structure"}
CRITICAL_SIGNALS = {"DXY", "US10Y", "Mega-cap leadership", "Semiconductors", "Breadth"}


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _fresh(signal: Any) -> bool:
    value = str(_get(signal, "freshness", "unknown") or "unknown").lower()
    return not any(x in value for x in ("missing", "error", "failed", "unavailable", "none"))


def _signals_map(forecast: Any) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for signal in list(_get(forecast, "signals", []) or []):
        name = str(_get(signal, "name", "") or "")
        if not name:
            continue
        out[name] = {
            "score": _f(_get(signal, "score", 0.0)),
            "weight": max(0.0, _f(_get(signal, "weight", 0.0))),
            "fresh": 1.0 if _fresh(signal) else 0.0,
        }
    return out


def _weighted_score(items: Iterable[Tuple[float, float]]) -> float:
    rows = [(float(s), max(0.0, float(w))) for s, w in items]
    den = sum(w for _, w in rows)
    return sum(s * w for s, w in rows) / den if den else 0.0


def _linear_slope(points: List[Tuple[datetime, float]]) -> float:
    """Return units per hour using a least-squares time slope."""
    if len(points) < 2:
        return 0.0
    t0 = points[0][0]
    xs = [(t - t0).total_seconds() / 3600.0 for t, _ in points]
    ys = [v for _, v in points]
    xbar = sum(xs) / len(xs)
    ybar = sum(ys) / len(ys)
    den = sum((x - xbar) ** 2 for x in xs)
    if den <= 1e-12:
        return 0.0
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / den


def _direction(value: float, deadband: float = 0.08) -> int:
    return 1 if value > deadband else -1 if value < -deadband else 0


def _history_read(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    except Exception:
        return []
    return rows[-MAX_HISTORY_ROWS:]


def _history_append(path: Path, row: Dict[str, Any], min_seconds: int = 120) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _history_read(path)
    if rows:
        last = rows[-1]
        if abs((_dt(row["timestamp"]) - _dt(last.get("timestamp"))).total_seconds()) < min_seconds:
            # Preserve time-series integrity: do not create artificial velocity from page refresh spam.
            return False
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
    return True


def snapshot_row(forecast: Any, snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    raw = snapshot or {}
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        raw = raw["data"]
    sigs = _signals_map(forecast)
    lead = _weighted_score(
        (v["score"], v["weight"]) for k, v in sigs.items()
        if k in LEADING_SIGNAL_NAMES and v["fresh"]
    )
    price = _weighted_score(
        (v["score"], v["weight"]) for k, v in sigs.items()
        if k in PRICE_SIGNAL_NAMES and v["fresh"]
    )
    return {
        "timestamp": str(_get(forecast, "generated_at", "") or datetime.now(timezone.utc).isoformat()),
        "direction": str(_get(forecast, "direction", "") or "").upper(),
        "bullish_probability": _f(_get(forecast, "bullish_probability", 50.0), 50.0),
        "confidence": _f(_get(forecast, "confidence", 0.0)),
        "score": _f(_get(forecast, "score", 0.0)),
        "regime": str(_get(forecast, "regime", "UNKNOWN") or "UNKNOWN").upper(),
        "data_coverage": _f(_get(forecast, "data_coverage", 0.0)),
        "intelligence_coverage": _f(_get(forecast, "intelligence_coverage", 0.0)),
        "nq_price": _f(raw.get("nq_futures_price"), 0.0) if isinstance(raw, dict) else 0.0,
        "leading_score": round(lead, 6),
        "price_score": round(price, 6),
        "signals": {k: round(v["score"], 6) if v["fresh"] else None for k, v in sigs.items()},
    }


def _signal_acceleration(history: List[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, float]:
    rows = (history + [current])[-8:]
    names = set()
    for row in rows:
        names.update((row.get("signals") or {}).keys())
    out = {}
    for name in names:
        pts = []
        for row in rows:
            value = (row.get("signals") or {}).get(name)
            if value is None:
                continue
            pts.append((_dt(row.get("timestamp")), _f(value)))
        if len(pts) >= 2:
            out[name] = round(_linear_slope(pts), 4)
    return out


def _alignment(signals: Dict[str, Dict[str, float]], target_sign: int) -> Tuple[float, List[str], List[str], List[str]]:
    aligned: List[str] = []
    opposed: List[str] = []
    missing: List[str] = []
    weights_aligned = 0.0
    weights_opposed = 0.0
    for name in LEADING_SIGNAL_NAMES:
        item = signals.get(name)
        if not item or not item["fresh"]:
            missing.append(name)
            continue
        d = _direction(item["score"])
        if d == 0:
            continue
        if d == target_sign:
            aligned.append(name)
            weights_aligned += item["weight"]
        else:
            opposed.append(name)
            weights_opposed += item["weight"]
    den = weights_aligned + weights_opposed
    ratio = weights_aligned / den if den else 0.5
    return ratio, aligned, opposed, missing


def _data_guard(forecast: Any, signals: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    data_cov = _f(_get(forecast, "data_coverage", 0.0))
    intel_cov = _f(_get(forecast, "intelligence_coverage", 0.0))
    critical_missing = [name for name in CRITICAL_SIGNALS if not signals.get(name) or not signals[name]["fresh"]]
    weak = data_cov < 0.65 or intel_cov < 0.40 or len(critical_missing) >= 3
    return {
        "pass": not weak,
        "data_coverage": round(data_cov, 3),
        "intelligence_coverage": round(intel_cov, 3),
        "critical_missing": sorted(critical_missing),
    }


def _regime_transition(history: List[Dict[str, Any]], current_regime: str) -> str:
    prior = [str(r.get("regime") or "UNKNOWN").upper() for r in history[-4:]]
    last = prior[-1] if prior else "UNKNOWN"
    if last == current_regime:
        return "STABLE"
    if last in {"BALANCED", "CONFLICTED"} and current_regime == "TRANSITION":
        return "EARLY_TRANSITION"
    if current_regime == "TREND" and last in {"BALANCED", "CONFLICTED", "TRANSITION"}:
        return "TREND_EMERGENCE"
    return f"{last}_TO_{current_regime}"


def _state(
    directional_pressure: float,
    prob_velocity: float,
    alignment: float,
    data_pass: bool,
    history_n: int,
    fragility: float,
) -> str:
    strength = abs(directional_pressure)
    rising = abs(prob_velocity) >= 3.0
    if not data_pass or history_n < 2:
        return "NO_EDGE"
    if strength >= 0.72 and alignment >= 0.72 and fragility <= 0.35:
        return "HIGH_CONVICTION_ALIGNMENT"
    if strength >= 0.52 and alignment >= 0.62:
        return "THESIS_DEVELOPING"
    if strength >= 0.32 and (rising or alignment >= 0.58):
        return "EARLY_WARNING"
    return "NO_EDGE"


def analyze_premove(
    forecast: Any,
    snapshot: Dict[str, Any] | None = None,
    history_path: Path | str = DEFAULT_HISTORY,
    record: bool = True,
) -> Dict[str, Any]:
    path = Path(history_path)
    history = _history_read(path)
    current = snapshot_row(forecast, snapshot)
    sigs = _signals_map(forecast)

    # Use only prior observations for velocity; current is appended analytically once.
    series = (history + [current])[-10:]
    prob_points = [(_dt(r.get("timestamp")), _f(r.get("bullish_probability"), 50.0)) for r in series]
    lead_points = [(_dt(r.get("timestamp")), _f(r.get("leading_score"), 0.0)) for r in series]
    price_points = [(_dt(r.get("timestamp")), _f(r.get("price_score"), 0.0)) for r in series]
    conf_points = [(_dt(r.get("timestamp")), _f(r.get("confidence"), 0.0)) for r in series]

    prob_velocity = _linear_slope(prob_points)
    lead_velocity = _linear_slope(lead_points)
    price_velocity = _linear_slope(price_points)
    confidence_velocity = _linear_slope(conf_points)

    lead_score = _f(current.get("leading_score"))
    price_score = _f(current.get("price_score"))
    # A positive divergence means leading evidence is ahead of price structure.
    lead_price_divergence = lead_score - price_score

    target_sign = 1 if lead_score >= 0 else -1
    alignment, aligned, opposed, missing = _alignment(sigs, target_sign)
    guard = _data_guard(forecast, sigs)

    consistency = _get(forecast, "consistency", {}) or {}
    conflict = _f(consistency.get("conflict"), 0.0) if isinstance(consistency, dict) else 0.0
    if conflict <= 0:
        # Conservative proxy when the truth object does not expose conflict.
        conflict = 1.0 - alignment

    # Fragility rises when evidence is opposed, critical inputs are missing, or confidence is weak.
    confidence = _f(current.get("confidence"))
    missing_penalty = min(0.40, len(guard["critical_missing"]) * 0.10)
    fragility = _clamp((1.0 - alignment) * 0.55 + missing_penalty + max(0.0, 55.0 - confidence) / 100.0, 0.0, 1.0)

    # Pre-move pressure deliberately emphasizes leading evidence and its acceleration.
    # NQ structure is present as a lag/confirmation term, not the dominant predictor.
    p_component = (current["bullish_probability"] - 50.0) / 45.0
    velocity_component = _clamp(prob_velocity / 18.0, -1.0, 1.0)
    lead_velocity_component = _clamp(lead_velocity / 0.70, -1.0, 1.0)
    divergence_component = _clamp(lead_price_divergence / 0.55, -1.0, 1.0)
    alignment_signed = (alignment * 2.0 - 1.0) * target_sign

    pressure = (
        0.34 * lead_score
        + 0.18 * p_component
        + 0.16 * velocity_component
        + 0.12 * lead_velocity_component
        + 0.10 * divergence_component
        + 0.10 * alignment_signed
    )
    pressure *= (1.0 - 0.45 * fragility)
    pressure = _clamp(pressure, -1.0, 1.0)

    # This is a research-layer probability, not a replacement for core FIA probability.
    raw_pre_prob = 100.0 * _sigmoid(2.65 * pressure)
    sample_penalty = min(1.0, max(0.0, len(history) / 8.0))
    pre_prob = 50.0 + (raw_pre_prob - 50.0) * sample_penalty
    if not guard["pass"]:
        pre_prob = 50.0 + (pre_prob - 50.0) * 0.45

    directional_pressure = pressure if pressure >= 0 else pressure
    state = _state(pressure, prob_velocity, alignment, guard["pass"], len(history), fragility)
    direction = "BULLISH" if pressure > 0.08 else "BEARISH" if pressure < -0.08 else "NEUTRAL"

    accelerations = _signal_acceleration(history, current)
    ranked_accel = sorted(accelerations.items(), key=lambda kv: abs(kv[1]), reverse=True)

    # Lead-time cannot be honestly claimed until high-frequency forward records resolve.
    validation = {
        "status": "FORWARD_VALIDATION_REQUIRED",
        "validated_early_warning_accuracy": None,
        "median_lead_time_minutes": None,
        "false_positive_rate": None,
        "note": "Do not claim pre-move accuracy/lead-time until this layer accumulates and resolves forward checkpoints.",
    }

    result = {
        "ok": True,
        "module": "FIA PRE-MOVE INTELLIGENCE",
        "research_only": True,
        "generated_at": current["timestamp"],
        "state": state,
        "direction": direction,
        "pre_move_probability": {
            "bullish": round(pre_prob, 1),
            "bearish": round(100.0 - pre_prob, 1),
            "calibration": "UNVALIDATED_DERIVED_LAYER",
        },
        "core_fia_probability": {
            "bullish": round(current["bullish_probability"], 1),
            "bearish": round(100.0 - current["bullish_probability"], 1),
        },
        "trajectory": {
            "bullish_probability_velocity_pp_per_hour": round(prob_velocity, 2),
            "leading_score_velocity_per_hour": round(lead_velocity, 4),
            "price_score_velocity_per_hour": round(price_velocity, 4),
            "confidence_velocity_pp_per_hour": round(confidence_velocity, 2),
            "leading_vs_price_divergence": round(lead_price_divergence, 4),
        },
        "evidence": {
            "leading_score": round(lead_score, 4),
            "price_confirmation_score": round(price_score, 4),
            "leading_alignment": round(alignment, 3),
            "aligned": aligned,
            "opposed": opposed,
            "missing": missing,
            "fastest_changing_signals": [{"name": n, "velocity_per_hour": v} for n, v in ranked_accel[:6]],
        },
        "risk_controls": {
            "fragility": round(fragility, 3),
            "data_guard": guard,
            "regime_transition": _regime_transition(history, current["regime"]),
            "no_edge_allowed": True,
            "broker_execution": False,
        },
        "history": {
            "observations_before_current": len(history),
            "minimum_for_velocity": 2,
            "recommended_for_stability": 8,
        },
        "validation": validation,
        "interpretation": (
            "Leading evidence is strengthening before NQ price structure fully confirms."
            if state in {"EARLY_WARNING", "THESIS_DEVELOPING"} and abs(lead_price_divergence) > 0.10
            else "Use this as an evidence-transition warning, not as a guaranteed price prediction."
        ),
    }

    if record:
        result["history"]["record_created"] = _history_append(path, current)
        result["history"]["path"] = str(path)
    return result


def premove_history(path: Path | str = DEFAULT_HISTORY, limit: int = 100) -> Dict[str, Any]:
    rows = _history_read(Path(path))
    return {"ok": True, "rows": rows[-max(1, min(int(limit), 1000)):], "count": len(rows)}
