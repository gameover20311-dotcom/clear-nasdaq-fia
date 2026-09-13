# CLEAR NASDAQ — FIA PRE-MOVE MAX RIGOR (Phase 32)
# Additive research layer. Never overwrites the core FIA probability or broker settings.
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

from .premove_engine import (
    DEFAULT_HISTORY,
    _clamp,
    _dt,
    _f,
    _get,
    _history_read,
    _linear_slope,
    analyze_premove,
    snapshot_row,
)
from .signal_identity import canonical_name_list, canonicalize_signal_keys

DEFAULT_MAX_HISTORY = Path(__file__).resolve().parents[1] / "fia_premove" / "data" / "premove_max_history.jsonl"

OPTIONAL_SIGNAL_ALIASES = {
    "US2Y": ("US2Y", "2Y", "US 2Y", "US02Y"),
    "VIX": ("VIX",),
    "VXN": ("VXN",),
    "REAL_YIELD": ("Real yields", "Real yield", "US10Y real yield"),
    "DEALER_GAMMA": ("Dealer gamma", "GEX", "Gamma exposure"),
    "ETF_FLOW": ("ETF flows", "QQQ flows", "ETF flow"),
    "SOX": ("SOX", "Semiconductor index", "SMH confirmation"),
    "OPTIONS_SKEW": ("Options skew", "QQQ skew", "Put/call skew"),
    "VOLUME_DELTA": ("Volume delta", "CVD", "Order-flow delta"),
    "FUTURES_BASIS": ("NQ basis", "Futures basis", "NQ-QQQ basis"),
    "NEWS_NOVELTY": ("News novelty", "Novelty score"),
    "CATALYST_SURPRISE": ("Catalyst surprise", "Surprise severity"),
    "MEGACAP_IMPACT": ("Mega-cap index impact", "Mega-cap contribution"),
    "SEMI_BREADTH": ("Semiconductor breadth", "Semi breadth"),
}


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 4:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    den = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    if den <= 1e-12:
        return None
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(dx, dy)) / den))


def _median_abs_dev(values: List[float]) -> float:
    if len(values) < 3:
        return 0.0
    med = statistics.median(values)
    return statistics.median(abs(x - med) for x in values)


def _change_point(values: List[float]) -> Dict[str, Any]:
    vals = [float(v) for v in values if v is not None]
    if len(vals) < 5:
        return {"detected": False, "z_like": 0.0, "direction": "NONE", "sample": len(vals)}
    diffs = [b - a for a, b in zip(vals[:-1], vals[1:])]
    baseline = diffs[:-1]
    last = diffs[-1]
    med = statistics.median(baseline) if baseline else 0.0
    mad = _median_abs_dev(baseline)
    scale = max(1e-6, 1.4826 * mad)
    z = (last - med) / scale
    detected = abs(z) >= 2.75
    return {
        "detected": detected,
        "z_like": round(z, 3),
        "direction": "UP" if z > 0 else "DOWN" if z < 0 else "NONE",
        "sample": len(vals),
    }


def _session_bucket(ts: Any) -> str:
    dt = _dt(ts).astimezone(ZoneInfo("America/New_York"))
    minutes = dt.hour * 60 + dt.minute
    if 4 * 60 <= minutes < 9 * 60 + 30:
        return "NY_PREMARKET"
    if 9 * 60 + 30 <= minutes < 11 * 60 + 30:
        return "NY_OPEN_DRIVE"
    if 11 * 60 + 30 <= minutes < 14 * 60:
        return "NY_MIDDAY"
    if 14 * 60 <= minutes < 16 * 60:
        return "NY_PM_POWER"
    if 16 * 60 <= minutes < 20 * 60:
        return "AFTER_HOURS"
    return "OVERNIGHT"


def _signed(v: float, deadband: float = 0.06) -> int:
    return 1 if v > deadband else -1 if v < -deadband else 0


def _persistence(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    signs = [_signed(_f(r.get("leading_score"))) for r in rows[-8:]]
    signs = [s for s in signs if s]
    if not signs:
        return {"ratio": 0.0, "direction": "NEUTRAL", "flips": 0, "sample": 0}
    pos = sum(s > 0 for s in signs)
    neg = sum(s < 0 for s in signs)
    dom = 1 if pos >= neg else -1
    ratio = max(pos, neg) / len(signs)
    flips = sum(a != b for a, b in zip(signs[:-1], signs[1:]))
    return {
        "ratio": round(ratio, 3),
        "direction": "BULLISH" if dom > 0 else "BEARISH",
        "flips": flips,
        "sample": len(signs),
    }


def _multi_window_slopes(rows: List[Dict[str, Any]], field: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for label, n in (("short", 3), ("medium", 6), ("long", 10)):
        pts = [(_dt(r.get("timestamp")), _f(r.get(field))) for r in rows[-n:]]
        out[label] = round(_linear_slope(pts), 5) if len(pts) >= 2 else 0.0
    return out


def _lead_lag_research(rows: List[Dict[str, Any]], max_rows: int = 40) -> List[Dict[str, Any]]:
    rows = rows[-max_rows:]
    names = sorted({k for r in rows for k, v in (r.get("signals") or {}).items() if v is not None})
    result = []
    for name in names:
        xs: List[float] = []
        ys: List[float] = []
        for i in range(len(rows) - 1):
            sig = (rows[i].get("signals") or {}).get(name)
            nxt_price = rows[i + 1].get("price_score")
            if sig is None or nxt_price is None:
                continue
            xs.append(_f(sig))
            ys.append(_f(nxt_price))
        corr = _pearson(xs, ys)
        if corr is not None:
            result.append({"signal": name, "lag1_correlation_to_next_price_score": round(corr, 3), "n": len(xs)})
    result.sort(key=lambda x: abs(x["lag1_correlation_to_next_price_score"]), reverse=True)
    return result[:8]


def _optional_inputs(forecast: Any) -> Dict[str, Any]:
    signals = list(_get(forecast, "signals", []) or [])
    by_name = {str(_get(s, "name", "") or "").strip().lower(): s for s in signals}
    out: Dict[str, Any] = {}
    for key, aliases in OPTIONAL_SIGNAL_ALIASES.items():
        found = None
        for alias in aliases:
            obj = by_name.get(alias.lower())
            if obj is not None:
                found = obj
                break
        if found is None:
            out[key] = {"status": "MISSING_NOT_FAKED", "score": None}
        else:
            freshness = str(_get(found, "freshness", "unknown") or "unknown")
            out[key] = {
                "status": "AVAILABLE" if not any(x in freshness.lower() for x in ("missing", "error", "unavailable", "failed")) else "UNAVAILABLE",
                "score": round(_f(_get(found, "score", 0.0)), 4),
                "freshness": freshness,
            }
    return out


def _extract_event_context(snapshot: Any) -> Dict[str, Any]:
    raw = snapshot or {}
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        raw = raw["data"]
    if not isinstance(raw, dict):
        return {"event_risk": "UNKNOWN", "minutes_to_event": None, "event": None}
    candidates = [
        raw.get("next_macro_event"), raw.get("macro_event"), raw.get("next_event"),
        raw.get("event"), raw.get("earnings_event")
    ]
    event = next((x for x in candidates if x not in (None, "", {})), None)
    mins = None
    for k in ("minutes_to_event", "next_event_minutes", "minutes_until_event"):
        if raw.get(k) not in (None, ""):
            mins = _f(raw.get(k))
            break
    risk = "NORMAL"
    if mins is not None:
        if mins <= 15:
            risk = "IMMINENT"
        elif mins <= 45:
            risk = "HIGH"
        elif mins <= 120:
            risk = "ELEVATED"
    return {"event_risk": risk, "minutes_to_event": mins, "event": event}


def _historical_analogs(rows: List[Dict[str, Any]], current: Dict[str, Any], limit: int = 5) -> Dict[str, Any]:
    # Uses only rows that precede the current timestamp. Similarity is transparent and deterministic.
    prior = [r for r in rows if _dt(r.get("timestamp")) < _dt(current.get("timestamp"))]
    if len(prior) < 8:
        return {"status": "INSUFFICIENT_HISTORY", "neighbors": []}
    # Canonical axes, de-duplicated: one signal can never occupy two axes.
    core_names = canonical_name_list(
        ["DXY", "US10Y", "Mega-cap leadership", "Semiconductors", "Breadth", "SPX confirmation"]
    )

    def vec(r: Dict[str, Any]) -> List[float]:
        # Read boundary: premove history rows written before the truthfulness
        # rename carry the legacy spelling. Files are not rewritten; they are
        # translated on read so historical and live vectors share one space.
        sig = canonicalize_signal_keys(r.get("signals") or {})
        return [
            _f(r.get("leading_score")),
            _f(r.get("price_score")),
            (_f(r.get("bullish_probability"), 50.0) - 50.0) / 50.0,
            *[_f(sig.get(n)) for n in core_names],
        ]

    cv = vec(current)
    candidates = []
    for r in prior[:-1]:
        rv = vec(r)
        d = math.sqrt(sum((a - b) ** 2 for a, b in zip(cv, rv)) / len(cv))
        same_regime = str(r.get("regime") or "") == str(current.get("regime") or "")
        if same_regime:
            d *= 0.88
        candidates.append((d, r))
    candidates.sort(key=lambda x: x[0])
    neighbors = []
    for d, r in candidates[:limit]:
        neighbors.append({
            "timestamp": r.get("timestamp"),
            "distance": round(d, 4),
            "regime": r.get("regime"),
            "leading_score": r.get("leading_score"),
            "price_score": r.get("price_score"),
        })
    return {"status": "AVAILABLE", "neighbors": neighbors}


def _expert_votes(base: Dict[str, Any], persistence: Dict[str, Any], change: Dict[str, Any], lead_lag: List[Dict[str, Any]]) -> Dict[str, Any]:
    t = base.get("trajectory") or {}
    e = base.get("evidence") or {}
    lead = _f(e.get("leading_score"))
    div = _f(t.get("leading_vs_price_divergence"))
    pv = _f(t.get("bullish_probability_velocity_pp_per_hour"))
    lv = _f(t.get("leading_score_velocity_per_hour"))
    align = _f(e.get("leading_alignment"), 0.5)
    votes = {
        "level": _signed(lead),
        "divergence": _signed(div),
        "probability_velocity": _signed(pv / 12.0),
        "leading_velocity": _signed(lv / 0.4),
        "alignment": (1 if lead >= 0 else -1) if align >= 0.62 else 0,
        "persistence": 1 if persistence.get("direction") == "BULLISH" and persistence.get("ratio", 0) >= 0.65 else -1 if persistence.get("direction") == "BEARISH" and persistence.get("ratio", 0) >= 0.65 else 0,
        "change_point": 1 if change.get("detected") and change.get("direction") == "UP" else -1 if change.get("detected") and change.get("direction") == "DOWN" else 0,
    }
    # Lead-lag evidence contributes only when history shows a meaningful relationship.
    strong = [x for x in lead_lag if abs(_f(x.get("lag1_correlation_to_next_price_score"))) >= 0.35]
    if strong:
        avg = sum(_f(x.get("lag1_correlation_to_next_price_score")) for x in strong) / len(strong)
        votes["historical_lead_lag"] = _signed(avg, 0.12)
    else:
        votes["historical_lead_lag"] = 0
    active = [v for v in votes.values() if v]
    if not active:
        return {"votes": votes, "agreement": 0.0, "direction": "NEUTRAL", "active_experts": 0}
    pos = sum(v > 0 for v in active)
    neg = sum(v < 0 for v in active)
    direction = "BULLISH" if pos > neg else "BEARISH" if neg > pos else "NEUTRAL"
    agreement = max(pos, neg) / len(active)
    return {"votes": votes, "agreement": round(agreement, 3), "direction": direction, "active_experts": len(active)}


def _counterfactual(base: Dict[str, Any], ensemble: Dict[str, Any], persistence: Dict[str, Any]) -> List[str]:
    e = base.get("evidence") or {}
    t = base.get("trajectory") or {}
    items = []
    align = _f(e.get("leading_alignment"), 0.5)
    fragility = _f((base.get("risk_controls") or {}).get("fragility"), 1.0)
    div = abs(_f(t.get("leading_vs_price_divergence")))
    if align < 0.70:
        items.append(f"Leading alignment needs to rise from {align:.2f} toward >=0.70 for stronger confirmation.")
    if fragility > 0.35:
        items.append(f"Fragility needs to fall from {fragility:.2f} toward <=0.35.")
    if persistence.get("ratio", 0.0) < 0.70:
        items.append("Directional persistence needs >=70% agreement across recent observations.")
    if div < 0.10:
        items.append("Leading-vs-price divergence is small; upstream evidence is not clearly ahead of price yet.")
    if ensemble.get("agreement", 0.0) < 0.75:
        items.append("Independent pre-move experts need >=75% directional agreement.")
    return items or ["Current evidence already satisfies the predeclared structural conditions; validation still governs probability claims."]


def _append_max_history(path: Path, row: Dict[str, Any], min_seconds: int = 120) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if path.exists():
        try:
            rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        except Exception:
            rows = []
    if rows and abs((_dt(row["timestamp"]) - _dt(rows[-1].get("timestamp"))).total_seconds()) < min_seconds:
        return False
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":"), sort_keys=True, default=str) + "\n")
    return True


def analyze_premove_max(
    forecast: Any,
    snapshot: Dict[str, Any] | None = None,
    history_path: Path | str = DEFAULT_HISTORY,
    max_history_path: Path | str = DEFAULT_MAX_HISTORY,
    record: bool = True,
) -> Dict[str, Any]:
    # Base layer is reused, but record=False avoids duplicate history writes.
    base = analyze_premove(forecast, snapshot, history_path=history_path, record=False)
    hist = _history_read(Path(history_path))
    current = snapshot_row(forecast, snapshot)
    rows = (hist + [current])[-60:]

    persistence = _persistence(rows)
    prob_slopes = _multi_window_slopes(rows, "bullish_probability")
    lead_slopes = _multi_window_slopes(rows, "leading_score")
    cp = _change_point([_f(r.get("leading_score")) for r in rows[-12:]])
    lag = _lead_lag_research(rows)
    ensemble = _expert_votes(base, persistence, cp, lag)
    analogs = _historical_analogs(rows, current)
    optional = _optional_inputs(forecast)
    event = _extract_event_context(snapshot)

    base_p = _f((base.get("pre_move_probability") or {}).get("bullish"), 50.0)
    base_strength = abs(base_p - 50.0) / 50.0
    ensemble_sign = 1 if ensemble["direction"] == "BULLISH" else -1 if ensemble["direction"] == "BEARISH" else 0
    base_sign = 1 if base_p > 50 else -1 if base_p < 50 else 0
    agreement = _f(ensemble.get("agreement"))
    persistence_ratio = _f(persistence.get("ratio"))
    fragility = _f((base.get("risk_controls") or {}).get("fragility"), 1.0)

    # Decision-strength is deliberately NOT called a calibrated probability.
    # It expresses evidence concentration under a frozen, predeclared formula.
    direction_consistency = 1.0 if ensemble_sign and ensemble_sign == base_sign else 0.0 if ensemble_sign == 0 else -1.0
    strength = (
        0.30 * base_strength
        + 0.24 * agreement
        + 0.18 * persistence_ratio
        + 0.12 * min(1.0, abs(lead_slopes["short"]) / 0.50)
        + 0.08 * min(1.0, abs(_f((base.get("trajectory") or {}).get("leading_vs_price_divergence"))) / 0.35)
        + 0.08 * max(0.0, direction_consistency)
    )
    strength *= max(0.0, 1.0 - 0.55 * fragility)
    if event["event_risk"] in {"IMMINENT", "HIGH"}:
        strength *= 0.82
    if not (base.get("risk_controls") or {}).get("data_guard", {}).get("pass", False):
        strength *= 0.45
    strength = _clamp(strength, 0.0, 1.0)

    state = "NO_EDGE"
    if strength >= 0.72 and agreement >= 0.75 and persistence_ratio >= 0.70:
        state = "PREMOVE_HIGH_ALIGNMENT"
    elif strength >= 0.52 and agreement >= 0.67:
        state = "PREMOVE_THESIS"
    elif strength >= 0.34 and agreement >= 0.58:
        state = "PREMOVE_EARLY_WARNING"

    if ensemble["direction"] == "NEUTRAL" or fragility >= 0.72:
        state = "NO_EDGE"

    # Hysteresis: escalation requires two recent compatible readings if available.
    max_path = Path(max_history_path)
    prior_max = []
    if max_path.exists():
        try:
            prior_max = [json.loads(x) for x in max_path.read_text(encoding="utf-8").splitlines() if x.strip()]
        except Exception:
            prior_max = []
    hysteresis = {"required_confirmations": 2, "confirmed": False, "prior_compatible": 0}
    if state != "NO_EDGE":
        compatible = 0
        for r in reversed(prior_max[-4:]):
            if r.get("direction") == ensemble["direction"] and r.get("state") != "NO_EDGE":
                compatible += 1
            else:
                break
        hysteresis["prior_compatible"] = compatible
        hysteresis["confirmed"] = compatible >= 1
        if not hysteresis["confirmed"] and state == "PREMOVE_HIGH_ALIGNMENT":
            state = "PREMOVE_THESIS"

    result = {
        "ok": True,
        "module": "FIA PRE-MOVE MAX RIGOR",
        "version": "32.0",
        "research_only": True,
        "broker_execution": False,
        "generated_at": current["timestamp"],
        "session": _session_bucket(current["timestamp"]),
        "direction": ensemble["direction"],
        "state": state,
        "decision_strength_0_100": round(strength * 100.0, 1),
        "probability_policy": {
            "status": "NOT_A_CALIBRATED_PROBABILITY",
            "reason": "Decision strength is kept separate from probability until forward/out-of-sample calibration proves mapping.",
            "core_probability_untouched": True,
        },
        "base_premove": base,
        "multi_window_trajectory": {
            "bullish_probability_slopes_pp_per_hour": prob_slopes,
            "leading_score_slopes_per_hour": lead_slopes,
            "change_point": cp,
        },
        "persistence_hysteresis": {
            "persistence": persistence,
            "hysteresis": hysteresis,
        },
        "ensemble": ensemble,
        "historical_lead_lag": lag,
        "historical_analogs": analogs,
        "event_context": event,
        "optional_institutional_inputs": optional,
        "counterfactual": _counterfactual(base, ensemble, persistence),
        "alert": {
            "fire": bool(
                state in {"PREMOVE_THESIS", "PREMOVE_HIGH_ALIGNMENT"}
                and hysteresis.get("confirmed")
                and (base.get("risk_controls") or {}).get("data_guard", {}).get("pass", False)
                and event.get("event_risk") != "IMMINENT"
            ),
            "severity": "HIGH" if state == "PREMOVE_HIGH_ALIGNMENT" and hysteresis.get("confirmed") else "MEDIUM" if state == "PREMOVE_THESIS" and hysteresis.get("confirmed") else "NONE",
            "reason": "Requires persistent multi-expert alignment, valid critical data and no imminent-event block.",
            "lead_time_minutes": None,
            "lead_time_status": "FORWARD_VALIDATION_REQUIRED",
        },
        "validation_gate": {
            "status": "FORWARD_AND_OOS_VALIDATION_REQUIRED",
            "no_90_percent_claim_without_evidence": True,
            "no_threshold_tuning_on_holdout": True,
            "configuration_should_be_frozen_before_replay": True,
        },
    }

    if record:
        # Let the original layer own its normal time-series history.
        analyze_premove(forecast, snapshot, history_path=history_path, record=True)
        slim = {
            "timestamp": current["timestamp"],
            "direction": result["direction"],
            "state": result["state"],
            "decision_strength_0_100": result["decision_strength_0_100"],
            "ensemble_agreement": result["ensemble"]["agreement"],
            "persistence_ratio": persistence["ratio"],
            "fragility": _f((base.get("risk_controls") or {}).get("fragility")),
            "session": result["session"],
        }
        result["max_history_record_created"] = _append_max_history(max_path, slim)
        result["max_history_path"] = str(max_path)
    return result
