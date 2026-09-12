"""Advanced research analytics for SIMONS SHADOW LAB V1.

This module is intentionally descriptive/research-only. It does not write to the
production Forward-OOS ledger, does not select or promote strategies, and never
changes a frozen shadow candidate. Every output carries an explicit NOT_PROVEN
status unless the caller layers a separate, predeclared validation protocol on top.
"""
from __future__ import annotations

import copy
import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .lab import LAB_SCHEMA_VERSION, _feature_map, _match_condition


def _float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        return out if math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def _clamp_probability(value: float) -> float:
    return min(1.0 - 1e-12, max(1e-12, value))


def _actual_binary(row: Mapping[str, Any], hours: int) -> Optional[int]:
    outcome = (row.get("outcomes") or {}).get(f"{hours}h") or {}
    actual = str(outcome.get("actual_direction") or "").upper()
    if actual == "BULLISH":
        return 1
    if actual == "BEARISH":
        return 0
    return None


def _probability_binary(row: Mapping[str, Any], hours: int) -> Optional[float]:
    features = _feature_map(dict(row), hours)
    p = _float(features.get("bullish_probability"))
    if p is None:
        return None
    return min(1.0, max(0.0, p / 100.0))


def calibration_report(
    rows: Sequence[Mapping[str, Any]],
    hours: int,
    bins: Sequence[Tuple[float, float]] = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.000001)),
) -> Dict[str, Any]:
    """Compute proper-scoring and calibration diagnostics on resolved rows only."""
    if hours not in (4, 8):
        raise ValueError("hours must be 4 or 8")

    resolved: List[Tuple[float, int]] = []
    for row in rows:
        y = _actual_binary(row, hours)
        p = _probability_binary(row, hours)
        if y is None or p is None:
            continue
        resolved.append((p, y))

    n = len(resolved)
    if not n:
        return {
            "schema_version": LAB_SCHEMA_VERSION,
            "horizon_hours": hours,
            "n": 0,
            "scientific_status": "INSUFFICIENT_SAMPLE_NOT_PROVEN",
            "brier_score": None,
            "log_loss": None,
            "ece": None,
            "baseline_brier_climatology": None,
            "skill_vs_climatology": None,
            "bins": [],
        }

    brier = sum((p - y) ** 2 for p, y in resolved) / n
    log_loss = -sum(y * math.log(_clamp_probability(p)) + (1 - y) * math.log(_clamp_probability(1 - p)) for p, y in resolved) / n
    climatology = sum(y for _, y in resolved) / n
    baseline_brier = sum((climatology - y) ** 2 for _, y in resolved) / n
    skill = None if baseline_brier <= 0 else 1.0 - (brier / baseline_brier)

    bin_rows: List[Dict[str, Any]] = []
    ece = 0.0
    for lo, hi in bins:
        vals = [(p, y) for p, y in resolved if lo <= p < hi]
        if not vals:
            continue
        mean_p = sum(p for p, _ in vals) / len(vals)
        actual_rate = sum(y for _, y in vals) / len(vals)
        gap = abs(mean_p - actual_rate)
        ece += (len(vals) / n) * gap
        bin_rows.append({
            "lower": lo,
            "upper": hi,
            "n": len(vals),
            "mean_forecast_probability": mean_p,
            "actual_bullish_rate": actual_rate,
            "absolute_calibration_gap": gap,
        })

    return {
        "schema_version": LAB_SCHEMA_VERSION,
        "horizon_hours": hours,
        "n": n,
        "brier_score": brier,
        "log_loss": log_loss,
        "ece": ece,
        "climatology_bullish_rate": climatology,
        "baseline_brier_climatology": baseline_brier,
        "skill_vs_climatology": skill,
        "bins": bin_rows,
        "scientific_status": "RESEARCH_DIAGNOSTIC_NOT_PROVEN" if n >= 30 else "INSUFFICIENT_SAMPLE_NOT_PROVEN",
        "warning": "In-sample/discovery calibration is descriptive and must not be presented as untouched forward validation.",
    }


def regime_report(rows: Sequence[Mapping[str, Any]], hours: int, min_group_n: int = 5) -> Dict[str, Any]:
    """Describe FIA directional performance by the regime that existed at lock time."""
    if hours not in (4, 8):
        raise ValueError("hours must be 4 or 8")
    groups: Dict[str, List[Tuple[bool, float, int]]] = defaultdict(list)

    for row in rows:
        y = _actual_binary(row, hours)
        p = _probability_binary(row, hours)
        if y is None or p is None:
            continue
        base = row.get("base") or {}
        regime = str(base.get("regime") or "UNKNOWN").upper()
        pred = 1 if p >= 0.5 else 0
        groups[regime].append((pred == y, p, y))

    out = []
    for regime, vals in sorted(groups.items()):
        n = len(vals)
        correct = sum(1 for c, _, _ in vals if c)
        brier = sum((p - y) ** 2 for _, p, y in vals) / n
        out.append({
            "regime": regime,
            "n": n,
            "correct": correct,
            "hit_rate": correct / n,
            "brier_score": brier,
            "eligible_for_interpretation": n >= min_group_n,
            "status": "EXPLORATORY_ONLY_NOT_PROVEN",
        })

    return {
        "schema_version": LAB_SCHEMA_VERSION,
        "horizon_hours": hours,
        "groups": out,
        "min_group_n": min_group_n,
        "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
        "warning": "Regime slicing increases multiplicity; small groups must not be promoted as edge.",
    }


def state_transition_report(rows: Sequence[Mapping[str, Any]], hours: int, min_group_n: int = 5) -> Dict[str, Any]:
    """Analyze previous-lock regime -> current-lock regime transitions.

    Both regimes exist before the current horizon outcome, so the transition is a
    causal research feature. Results remain discovery-only until frozen and tested
    on observations occurring after freeze.
    """
    if hours not in (4, 8):
        raise ValueError("hours must be 4 or 8")
    ordered = sorted(rows, key=lambda r: str(r.get("locked_at_utc") or ""))
    groups: Dict[str, List[int]] = defaultdict(list)

    previous_regime: Optional[str] = None
    for row in ordered:
        current_regime = str((row.get("base") or {}).get("regime") or "UNKNOWN").upper()
        y = _actual_binary(row, hours)
        if previous_regime is not None and y is not None:
            groups[f"{previous_regime}->{current_regime}"].append(y)
        previous_regime = current_regime

    transitions = []
    for transition, ys in sorted(groups.items()):
        n = len(ys)
        bullish = sum(ys)
        transitions.append({
            "transition": transition,
            "n": n,
            "bullish_outcomes": bullish,
            "bearish_outcomes": n - bullish,
            "bullish_rate": bullish / n,
            "eligible_for_interpretation": n >= min_group_n,
            "status": "EXPLORATORY_ONLY_NOT_PROVEN",
        })

    return {
        "schema_version": LAB_SCHEMA_VERSION,
        "horizon_hours": hours,
        "transitions": transitions,
        "min_group_n": min_group_n,
        "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
        "automatic_candidate_generation": False,
    }


def _evaluate_candidate_spec(spec: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    hours = int(spec.get("horizon_hours") or 0)
    predicted_direction = str(spec.get("predicted_direction") or "").upper()
    conditions = list(spec.get("conditions") or [])
    selected = []

    for raw_row in rows:
        row = dict(raw_row)
        actual_binary = _actual_binary(row, hours)
        if actual_binary is None:
            continue
        features = _feature_map(row, hours)
        if not all(_match_condition(features, cond) for cond in conditions):
            continue
        direction = predicted_direction
        if direction == "FOLLOW_FIA":
            direction = str(features.get("fia_direction") or "").upper()
        if direction not in {"BULLISH", "BEARISH"}:
            continue
        actual = "BULLISH" if actual_binary == 1 else "BEARISH"
        selected.append(direction == actual)

    n = len(selected)
    correct = sum(1 for x in selected if x)
    return {"n": n, "correct": correct, "hit_rate": (correct / n) if n else None}


def parameter_robustness_report(
    candidate: Mapping[str, Any],
    discovery_rows: Sequence[Mapping[str, Any]],
    relative_steps: Sequence[float] = (-0.10, -0.05, 0.0, 0.05, 0.10),
) -> Dict[str, Any]:
    """Perturb numeric threshold conditions on discovery data only.

    This is a fragility diagnostic, not validation. It helps identify a rule that
    works only at one knife-edge threshold, which is a classic overfitting smell.
    """
    base_spec = copy.deepcopy(candidate.get("spec") or candidate)
    variants: List[Dict[str, Any]] = []

    numeric_condition_indexes = []
    for idx, cond in enumerate(base_spec.get("conditions") or []):
        if str(cond.get("op") or "") in {"gte", "lte", "gt", "lt"} and _float(cond.get("value")) is not None:
            numeric_condition_indexes.append(idx)

    if not numeric_condition_indexes:
        evaluation = _evaluate_candidate_spec(base_spec, discovery_rows)
        return {
            "schema_version": LAB_SCHEMA_VERSION,
            "variants": [{"label": "BASE", "spec": base_spec, **evaluation}],
            "scientific_status": "DISCOVERY_ROBUSTNESS_ONLY_NOT_VALIDATION",
            "warning": "No numeric threshold conditions were available to perturb.",
        }

    # One-at-a-time perturbations avoid an exponential parameter search explosion.
    variants.append({"label": "BASE", "spec": base_spec, **_evaluate_candidate_spec(base_spec, discovery_rows)})
    for idx in numeric_condition_indexes:
        original = float(base_spec["conditions"][idx]["value"])
        for step in relative_steps:
            if step == 0.0:
                continue
            spec = copy.deepcopy(base_spec)
            delta = max(abs(original) * abs(step), 1.0)
            spec["conditions"][idx]["value"] = original + (delta if step > 0 else -delta)
            evaluation = _evaluate_candidate_spec(spec, discovery_rows)
            variants.append({
                "label": f"COND_{idx}_{step:+.0%}",
                "changed_condition_index": idx,
                "relative_step": step,
                "spec": spec,
                **evaluation,
            })

    nonempty_rates = [v["hit_rate"] for v in variants if v.get("n", 0) > 0 and v.get("hit_rate") is not None]
    spread = (max(nonempty_rates) - min(nonempty_rates)) if nonempty_rates else None
    return {
        "schema_version": LAB_SCHEMA_VERSION,
        "method": "ONE_AT_A_TIME_THRESHOLD_PERTURBATION",
        "variants": variants,
        "hit_rate_range": [min(nonempty_rates), max(nonempty_rates)] if nonempty_rates else None,
        "hit_rate_spread": spread,
        "scientific_status": "DISCOVERY_ROBUSTNESS_ONLY_NOT_VALIDATION",
        "warning": "Robustness on discovery data does not prove predictive edge; post-freeze validation remains mandatory.",
    }


def candidate_forward_metrics(
    shadow_events: Sequence[Mapping[str, Any]],
    round_trip_cost_points: float = 0.0,
) -> Dict[str, Any]:
    """Evaluate immutable shadow FIRE decisions after their separate resolutions.

    Cost is expressed only in generic NQ points per completed round trip; this
    function does not size positions, model leverage, or give trading instructions.
    """
    if round_trip_cost_points < 0:
        raise ValueError("round_trip_cost_points must be >= 0")

    decisions = {str(e.get("forecast_id")): e for e in shadow_events if e.get("event_type") == "DECISION_LOCK"}
    resolutions = {str(e.get("forecast_id")): e for e in shadow_events if e.get("event_type") == "DECISION_RESOLUTION"}
    samples: List[Dict[str, Any]] = []

    for fid, decision in decisions.items():
        dp = decision.get("payload") or {}
        if dp.get("decision") != "FIRE":
            continue
        resolution = resolutions.get(fid)
        if resolution is None:
            continue
        rp = resolution.get("payload") or {}
        predicted = str(rp.get("predicted_direction") or dp.get("predicted_direction") or "").upper()
        entry = _float(rp.get("entry_price"))
        outcome = _float(rp.get("outcome_price"))
        if predicted not in {"BULLISH", "BEARISH"} or entry is None or outcome is None:
            continue
        signed_move = (outcome - entry) if predicted == "BULLISH" else (entry - outcome)
        samples.append({
            "forecast_id": fid,
            "decision_created_at_utc": decision.get("created_at_utc"),
            "correct": rp.get("correct"),
            "gross_points": signed_move,
            "net_points_after_assumed_friction": signed_move - round_trip_cost_points,
        })

    samples.sort(key=lambda x: str(x.get("decision_created_at_utc") or ""))
    n = len(samples)
    correct = sum(1 for s in samples if s.get("correct") is True)
    gross_avg = sum(s["gross_points"] for s in samples) / n if n else None
    net_avg = sum(s["net_points_after_assumed_friction"] for s in samples) / n if n else None

    early_late = None
    if n >= 4:
        cut = n // 2
        early = samples[:cut]
        late = samples[cut:]
        def _segment(vals: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
            sn = len(vals)
            sc = sum(1 for x in vals if x.get("correct") is True)
            return {
                "n": sn,
                "hit_rate": sc / sn if sn else None,
                "avg_net_points": sum(float(x["net_points_after_assumed_friction"]) for x in vals) / sn if sn else None,
            }
        early_late = {"early": _segment(early), "late": _segment(late)}

    if n < 30:
        status = "INSUFFICIENT_SAMPLE_NOT_PROVEN"
    elif n < 50:
        status = "FORWARD_VALIDATING_NOT_PROVEN"
    else:
        status = "RESEARCH_REVIEW_ELIGIBLE_NOT_PRODUCTION_APPROVED"

    return {
        "schema_version": LAB_SCHEMA_VERSION,
        "resolved_fires": n,
        "correct": correct,
        "hit_rate": correct / n if n else None,
        "gross_average_points": gross_avg,
        "assumed_round_trip_cost_points": round_trip_cost_points,
        "net_average_points_after_assumed_friction": net_avg,
        "early_vs_late": early_late,
        "samples": samples,
        "candidate_status": status,
        "predictive_edge_proven": False,
        "automatic_production_promotion": False,
        "warning": "Friction is an explicit scenario assumption, not a measured execution cost. Forward sample size and stability remain mandatory.",
    }


def full_research_diagnostic(
    rows: Sequence[Mapping[str, Any]],
    hours: int,
) -> Dict[str, Any]:
    """Convenience bundle for a frozen research snapshot."""
    return {
        "schema_version": LAB_SCHEMA_VERSION,
        "horizon_hours": hours,
        "calibration": calibration_report(rows, hours),
        "regimes": regime_report(rows, hours),
        "state_transitions": state_transition_report(rows, hours),
        "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
        "automatic_strategy_selection": False,
    }
