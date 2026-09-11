"""Predeclared causal-feature discovery for SIMONS SHADOW LAB V2 hybrid.

Every result is exploratory. V2 keeps the existing real-schema/state-transition
work and adds whole-grid accounting, Bonferroni + BH reporting, a reproducible
grid hash, search-budget fail-closed behaviour, and a search-wide permutation
null so the cost of trying many rules is visible.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Sequence

from .causal_features import extract_lock_time_features, state_signature
from .lab import LAB_SCHEMA_VERSION, _float, canonical_bytes, sha256_bytes
from .scientific_stats import (
    bh_qvalues,
    binomial_upper_tail,
    bonferroni,
    search_wide_permutation_null,
    wilson_interval,
)


def _actual(row: Mapping[str, Any], hours: int) -> str:
    return str(((row.get("outcomes") or {}).get(f"{hours}h") or {}).get("actual_direction") or "").upper()


def discover_causal_grid(
    rows: Sequence[Dict[str, Any]],
    min_n: int = 12,
    permutations: int = 200,
    permutation_seed: int = 20260911,
    max_tests: int = 10000,
) -> Dict[str, Any]:
    regimes = sorted({str((r.get("base") or {}).get("regime") or "UNKNOWN").upper() for r in rows})
    regime_options = ["ANY"] + regimes
    probability_thresholds = (55.0, 60.0, 65.0)
    confidence_thresholds = (20.0, 40.0, 60.0)
    alignment_thresholds = (0, 3, 5)
    agreement_options = ("ANY", "AGREE")
    search_space = {
        "probability_thresholds": list(probability_thresholds),
        "confidence_thresholds": list(confidence_thresholds),
        "alignment_thresholds": list(alignment_thresholds),
        "regimes": regime_options,
        "agreement_options": list(agreement_options),
        "horizons": [4, 8],
        "directions": ["BULLISH", "BEARISH"],
    }
    expected_tests = (
        2 * 2 * len(probability_thresholds) * len(confidence_thresholds)
        * len(alignment_thresholds) * len(regime_options) * len(agreement_options)
    )
    if expected_tests > int(max_tests):
        raise RuntimeError(f"declared search space exceeds budget: {expected_tests}>{max_tests}")
    grid_hash = sha256_bytes(canonical_bytes(search_space))

    # Precompute features once per row/horizon. Outcome access stays separate
    # from feature extraction, preserving the mechanical lock-time barrier.
    features_by_h = {h: [extract_lock_time_features(r, h) for r in rows] for h in (4, 8)}
    outcomes_by_h = {h: [_actual(r, h) for r in rows] for h in (4, 8)}

    results: List[Dict[str, Any]] = []
    rule_masks: List[Dict[str, Any]] = []
    for hours in (4, 8):
        outcomes = outcomes_by_h[hours]
        for direction in ("BULLISH", "BEARISH"):
            prob_field = "bullish_probability" if direction == "BULLISH" else "bearish_probability"
            for pthr in probability_thresholds:
                for cthr in confidence_thresholds:
                    for athr in alignment_thresholds:
                        for regime in regime_options:
                            for agreement in agreement_options:
                                indexes: List[int] = []
                                ids: List[str] = []
                                correct = 0
                                for idx, (row, f, actual) in enumerate(zip(rows, features_by_h[hours], outcomes)):
                                    if actual not in {"BULLISH", "BEARISH"}:
                                        continue
                                    pval = _float(f.get(prob_field)); conf = _float(f.get("confidence"))
                                    align = int(f.get("component_alignment_count") or 0)
                                    if pval is None or conf is None or pval < pthr or conf < cthr or align < athr:
                                        continue
                                    if regime != "ANY" and f.get("regime") != regime:
                                        continue
                                    if agreement == "AGREE" and not f.get("horizon_agreement"):
                                        continue
                                    indexes.append(idx)
                                    ids.append(str(row.get("forecast_id") or ""))
                                    correct += int(actual == direction)
                                n = len(indexes)
                                pvalue = binomial_upper_tail(correct, n, 0.5) if n >= min_n else 1.0
                                low, high = wilson_interval(correct, n)
                                result = {
                                    "horizon_hours": hours,
                                    "predicted_direction": direction,
                                    "conditions": {
                                        prob_field: {"gte": pthr},
                                        "confidence": {"gte": cthr},
                                        "component_alignment_count": {"gte": athr},
                                        "regime": regime,
                                        "horizon_agreement": agreement,
                                    },
                                    "n": n,
                                    "correct": correct,
                                    "hit_rate": correct / n if n else None,
                                    "wilson_95": [low, high],
                                    "p_value_vs_50pct": pvalue,
                                    "eligible_min_n": n >= min_n,
                                    "discovery_forecast_ids": ids,
                                }
                                results.append(result)
                                rule_masks.append({
                                    "horizon_hours": hours,
                                    "predicted_direction": direction,
                                    "selected_indexes": indexes,
                                })

    tests_run = len(results)
    if tests_run != expected_tests:
        raise RuntimeError(f"search accounting mismatch: expected={expected_tests} actual={tests_run}")
    qvalues = bh_qvalues([float(r["p_value_vs_50pct"]) for r in results])
    null = search_wide_permutation_null(
        outcomes_by_horizon=outcomes_by_h,
        rule_masks=rule_masks,
        permutations=permutations,
        seed=permutation_seed,
        min_n=min_n,
    )
    maxima = list(null.get("maxima") or [])
    for result, q in zip(results, qvalues):
        p = float(result["p_value_vs_50pct"])
        hit = result.get("hit_rate")
        empirical = None
        if hit is not None and maxima:
            empirical = (1.0 + sum(1 for x in maxima if float(x) >= float(hit))) / (len(maxima) + 1.0)
        result["bh_q_value"] = q
        result["bonferroni_p_value"] = bonferroni(p, tests_run)
        result["search_wide_permutation_p_value"] = empirical
        result["survives_bh_05"] = bool(result["eligible_min_n"] and q <= 0.05)
        result["survives_bonferroni_05"] = bool(result["eligible_min_n"] and result["bonferroni_p_value"] <= 0.05)
        result["survives_search_wide_05"] = bool(result["eligible_min_n"] and empirical is not None and empirical <= 0.05)
        result["robust_discovery_screen"] = bool(result["survives_bh_05"] and result["survives_search_wide_05"])
        result["status"] = "EXPLORATORY_ONLY_NOT_PROVEN"

    compact_null = dict(null)
    compact_null.pop("maxima", None)
    return {
        "schema_version": LAB_SCHEMA_VERSION,
        "method": "PREDECLARED_CAUSAL_FEATURE_GRID_V2_HYBRID",
        "search_space": search_space,
        "grid_hash": grid_hash,
        "tests_run": tests_run,
        "full_grid_is_multiplicity_denominator": True,
        "min_n": min_n,
        "multiple_testing_control": ["BENJAMINI_HOCHBERG", "BONFERRONI", "SEARCH_WIDE_PERMUTATION_NULL"],
        "search_wide_permutation_null": compact_null,
        "automatic_candidate_selection": False,
        "results": results,
        "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
        "warning": "Discovery survivors are hypotheses only; candidate freeze and genuinely new post-freeze validation remain mandatory.",
    }


def state_distribution(rows: Sequence[Dict[str, Any]], hours: int) -> Dict[str, Any]:
    counts: Counter[str] = Counter(state_signature(extract_lock_time_features(row, hours)) for row in rows)
    return {
        "horizon_hours": hours,
        "states": [{"state": key, "n": n} for key, n in counts.most_common()],
        "automatic_strategy_selection": False,
        "scientific_status": "DESCRIPTIVE_ONLY_NOT_PROVEN",
    }


def state_transition_candidates(rows: Sequence[Dict[str, Any]], hours: int, min_n: int = 12) -> Dict[str, Any]:
    ordered = sorted(rows, key=lambda r: str(r.get("locked_at_utc") or ""))
    buckets: Dict[str, Dict[str, int]] = {}
    for prev, curr in zip(ordered, ordered[1:]):
        a = state_signature(extract_lock_time_features(prev, hours))
        b = state_signature(extract_lock_time_features(curr, hours))
        actual = _actual(curr, hours)
        key = f"{a} -> {b}"
        bucket = buckets.setdefault(key, {"n": 0, "bullish": 0, "bearish": 0})
        if actual in {"BULLISH", "BEARISH"}:
            bucket["n"] += 1
            bucket["bullish" if actual == "BULLISH" else "bearish"] += 1
    items = []
    for transition, bucket in sorted(buckets.items()):
        n = bucket["n"]
        majority = max(bucket["bullish"], bucket["bearish"])
        pvalue = binomial_upper_tail(majority, n, 0.5) if n >= min_n else 1.0
        low, high = wilson_interval(majority, n)
        items.append({
            "transition": transition,
            **bucket,
            "majority_direction": "BULLISH" if bucket["bullish"] > bucket["bearish"] else "BEARISH" if bucket["bearish"] > bucket["bullish"] else "TIE",
            "p_value_majority_vs_50pct": pvalue,
            "wilson_95_majority_rate": [low, high],
            "eligible_min_n": n >= min_n,
            "status": "EXPLORATORY_ONLY_NOT_PROVEN",
        })
    qvalues = bh_qvalues([float(i["p_value_majority_vs_50pct"]) for i in items])
    for item, q in zip(items, qvalues):
        item["bh_q_value"] = q
        item["bonferroni_p_value"] = bonferroni(item["p_value_majority_vs_50pct"], len(items)) if items else 1.0
    return {
        "horizon_hours": hours,
        "transitions": items,
        "tests_run": len(items),
        "multiple_testing_control": ["BENJAMINI_HOCHBERG", "BONFERRONI"],
        "automatic_candidate_generation": False,
        "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
    }
