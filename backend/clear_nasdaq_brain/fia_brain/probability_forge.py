from __future__ import annotations

"""Deterministic probability integrity layer for CLEAR NASDAQ FIA.

This module does NOT invent market evidence and does NOT claim empirical calibration.
It can only reconcile/shrink an already-grounded forecast using independent advisory
layers that were produced from the same prediction-time evidence snapshot.

Design goals:
- resist one-agent probability outliers;
- penalize disagreement / regime novelty / single-driver fragility;
- require independent evidence clusters for directional conviction;
- avoid false precision when no fitted calibration profile exists;
- never increase confidence beyond upstream caps;
- keep a reproducible probability provenance hash.
"""

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .util import sha256_obj


def _clamp(x: Any, lo: float = 0.0, hi: float = 100.0) -> float:
    try:
        v = float(x)
    except Exception:
        v = 50.0
    if v != v or v in (float("inf"), float("-inf")):
        v = 50.0
    return max(lo, min(hi, v))


def _weighted_median(values: Sequence[Tuple[float, float]]) -> float:
    rows = sorted((float(v), max(0.0, float(w))) for v, w in values)
    total = sum(w for _, w in rows)
    if total <= 0:
        return 50.0
    target = total / 2.0
    acc = 0.0
    for v, w in rows:
        acc += w
        if acc >= target:
            return v
    return rows[-1][0]


def _scenario_anchor(scenarios: Mapping[str, Any]) -> float:
    """Map BULL/BASE/BEAR lattice to a symmetric bullish probability anchor.

    BASE contributes 0.5 because it explicitly represents conflicted/range/no-edge,
    not a hidden directional forecast.
    """
    worlds = scenarios.get("worlds") if isinstance(scenarios, Mapping) else None
    if not isinstance(worlds, list):
        return 50.0
    probs = {str(w.get("kind", "")).upper(): _clamp(w.get("probability", 0)) for w in worlds if isinstance(w, Mapping)}
    if not {"BULL", "BASE", "BEAR"}.issubset(probs):
        return 50.0
    total = probs["BULL"] + probs["BASE"] + probs["BEAR"]
    if total <= 0:
        return 50.0
    return 100.0 * (probs["BULL"] + 0.5 * probs["BASE"]) / total


def _tribunal_quality(tribunal: Mapping[str, Any]) -> float:
    if not isinstance(tribunal, Mapping):
        return 0.5
    vals = [
        _clamp(tribunal.get("grounding_score", 50)) / 100.0,
        _clamp(tribunal.get("causal_score", 50)) / 100.0,
        _clamp(tribunal.get("uncertainty_score", 50)) / 100.0,
    ]
    return max(0.1, min(1.0, sum(vals) / len(vals)))


def _independent_cluster_count(evidence_ids: Iterable[Any], cluster_of: Optional[Mapping[str, str]]) -> int:
    ids = {str(x) for x in evidence_ids or []}
    if not ids:
        return 0
    if not cluster_of:
        return len(ids)
    return len({str(cluster_of.get(eid, eid)) for eid in ids})


def _empirical_profile_is_mature(profile: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(profile, Mapping) or not profile.get("enabled"):
        return False
    try:
        return int(profile.get("resolved_n", 0)) >= 50
    except Exception:
        return False


def forge(
    chief: Mapping[str, Any],
    consensus: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    tribunal: Mapping[str, Any],
    metacognition: Mapping[str, Any],
    interventions: Mapping[str, Any],
    source_quality: Mapping[str, Any],
    cluster_of: Optional[Mapping[str, str]] = None,
    calibration_profile: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (hardened_final, provenance).

    The returned object keeps the upstream analysis schema. The forge is
    intentionally asymmetric: it may reduce directional conviction, but it
    cannot manufacture a new directional thesis from a NO_EDGE/NEUTRAL chief.
    """
    out: Dict[str, Any] = deepcopy(dict(chief))

    chief_p = _clamp(out.get("bullish_probability", 50))
    consensus_p = _clamp(consensus.get("bullish_probability", 50))
    scenario_p = _scenario_anchor(scenarios)
    tq = _tribunal_quality(tribunal)
    spread = _clamp(consensus.get("probability_spread_std", 0))
    entropy = max(0.0, min(1.0, float(scenarios.get("entropy", 1.0) if isinstance(scenarios, Mapping) else 1.0)))
    overall_unc = _clamp(metacognition.get("overall_uncertainty", 0)) if isinstance(metacognition, Mapping) else 0.0

    # Upstream chief remains the strongest anchor only when tribunal quality is high.
    anchors = [
        (chief_p, 1.0 + 0.8 * tq),
        (consensus_p, 1.15),
        (scenario_p, 0.65 + 0.55 * (1.0 - entropy)),
    ]
    med = _weighted_median(anchors)

    # Huber-style clipping prevents one advisory layer from pulling the fusion
    # more than 18 points away from the robust center.
    clipped = [(max(med - 18.0, min(med + 18.0, p)), w) for p, w in anchors]
    denom = sum(w for _, w in clipped) or 1.0
    fused = sum(p * w for p, w in clipped) / denom

    # Epistemic shrinkage: disagreement, uncertainty, scenario entropy and
    # single-driver fragility all pull probability toward 50 rather than merely
    # hiding the problem inside a confidence score.
    shrink = 0.0
    shrink += min(0.22, spread / 180.0)
    shrink += min(0.18, overall_unc / 500.0)
    shrink += min(0.10, entropy * 0.10)
    if isinstance(interventions, Mapping) and interventions.get("fragile_to_single_driver"):
        shrink += 0.10
    if isinstance(source_quality, Mapping):
        cap = _clamp(source_quality.get("confidence_cap", 100))
        if cap < 70:
            shrink += min(0.12, (70.0 - cap) / 250.0)
    shrink = max(0.0, min(0.48, shrink))
    shrunk = 50.0 + (fused - 50.0) * (1.0 - shrink)

    supporting_clusters = _independent_cluster_count(out.get("evidence_ids", []), cluster_of)
    counter_clusters = _independent_cluster_count(out.get("counter_evidence_ids", []), cluster_of)

    # Evidence-capacity ceiling. Without mature empirical calibration, extreme
    # probabilities require multiple independent support clusters.
    mature = _empirical_profile_is_mature(calibration_profile)
    if mature:
        max_dev = 30.0
    else:
        if supporting_clusters <= 1:
            max_dev = 8.0
        elif supporting_clusters == 2:
            max_dev = 12.0
        elif supporting_clusters == 3:
            max_dev = 16.0
        elif supporting_clusters == 4:
            max_dev = 20.0
        else:
            max_dev = 25.0
    final_p = max(50.0 - max_dev, min(50.0 + max_dev, shrunk))

    prior_direction = str(out.get("direction", "NO_EDGE")).upper()
    derived = "BULLISH" if final_p >= 56.0 else ("BEARISH" if final_p <= 44.0 else "NO_EDGE")

    # The forge can only weaken conviction. It never flips a directional thesis
    # into the opposite side; conflict becomes NO_EDGE instead.
    if prior_direction in {"NEUTRAL", "NO_EDGE"}:
        direction = "NO_EDGE"
    elif prior_direction == "BULLISH" and derived == "BEARISH":
        direction = "NO_EDGE"
    elif prior_direction == "BEARISH" and derived == "BULLISH":
        direction = "NO_EDGE"
    else:
        direction = derived

    # A directional result needs at least two independent prediction-time support
    # clusters. This is stricter than merely citing multiple scalar fields.
    if direction in {"BULLISH", "BEARISH"} and supporting_clusters < 2:
        direction = "NO_EDGE"
        final_p = 50.0 + (final_p - 50.0) * 0.45

    # High uncertainty / very large model spread is an explicit abstention state.
    if overall_unc >= 78.0 or spread >= 26.0:
        direction = "NO_EDGE"
        final_p = 50.0 + (final_p - 50.0) * 0.50

    out["direction"] = direction
    out["bullish_probability"] = round(final_p, 2)
    out["bearish_probability"] = round(100.0 - final_p, 2)

    # Confidence is capped, never increased.
    conf = _clamp(out.get("confidence", 0))
    conf_caps = [conf]
    if isinstance(metacognition, Mapping):
        conf_caps.append(_clamp(metacognition.get("confidence_cap", 100)))
    if isinstance(tribunal, Mapping):
        conf_caps.append(_clamp(tribunal.get("recommended_confidence_cap", 100)))
    if isinstance(source_quality, Mapping):
        conf_caps.append(_clamp(source_quality.get("confidence_cap", 100)))
    if direction == "NO_EDGE":
        conf_caps.append(55.0)
    if supporting_clusters < 2:
        conf_caps.append(40.0)
    out["confidence"] = round(min(conf_caps), 2)

    unknowns = list(out.get("unknowns") or [])
    if shrink >= 0.30 and "probability_forge_high_epistemic_shrinkage" not in unknowns:
        unknowns.append("probability_forge_high_epistemic_shrinkage")
    if supporting_clusters < 2 and "insufficient_independent_support_clusters" not in unknowns:
        unknowns.append("insufficient_independent_support_clusters")
    out["unknowns"] = unknowns[:20]

    provenance: Dict[str, Any] = {
        "engine": "SOL56_PROBABILITY_FORGE_V7_2",
        "chief_probability": round(chief_p, 2),
        "consensus_probability": round(consensus_p, 2),
        "scenario_anchor_probability": round(scenario_p, 2),
        "weighted_median": round(med, 2),
        "pre_shrink_fused_probability": round(fused, 2),
        "epistemic_shrinkage": round(shrink, 4),
        "supporting_independent_clusters": supporting_clusters,
        "counter_independent_clusters": counter_clusters,
        "probability_spread_std": round(spread, 2),
        "scenario_entropy": round(entropy, 4),
        "overall_uncertainty": round(overall_unc, 2),
        "tribunal_quality": round(tq, 4),
        "mature_empirical_calibration": mature,
        "max_probability_deviation_from_50": round(max_dev, 2),
        "final_direction": direction,
        "final_bullish_probability": out["bullish_probability"],
        "final_bearish_probability": out["bearish_probability"],
        "final_confidence": out["confidence"],
        "policy": {
            "may_create_new_direction": False,
            "may_flip_direction": False,
            "may_only_shrink_or_abstain": True,
            "minimum_independent_clusters_for_direction": 2,
        },
    }
    provenance["probability_provenance_sha256"] = sha256_obj(provenance)
    return out, provenance
