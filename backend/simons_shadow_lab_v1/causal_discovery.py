"""Predeclared causal-feature discovery for SIMONS SHADOW LAB V1.

Every result is exploratory. Nothing here auto-selects, freezes or promotes a
strategy.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Mapping, Sequence

from .causal_features import extract_lock_time_features, state_signature
from .lab import LAB_SCHEMA_VERSION, _float


def _binomial_upper_tail(k: int, n: int, p: float = 0.5) -> float:
    if n <= 0 or k < 0 or k > n:
        return 1.0
    return min(1.0, sum(math.comb(n, i) * p**i * (1-p)**(n-i) for i in range(k, n+1)))


def _bh_qvalues(pvalues: Sequence[float]) -> List[float]:
    m = len(pvalues)
    if not m:
        return []
    order = sorted(enumerate(pvalues), key=lambda pair: pair[1])
    q = [1.0] * m
    running = 1.0
    for j in range(m - 1, -1, -1):
        idx, p = order[j]
        running = min(running, p * m / (j + 1))
        q[idx] = min(1.0, running)
    return q


def _actual(row: Mapping[str, Any], hours: int) -> str:
    return str(((row.get("outcomes") or {}).get(f"{hours}h") or {}).get("actual_direction") or "").upper()


def discover_causal_grid(rows: Sequence[Dict[str, Any]], min_n: int = 12) -> Dict[str, Any]:
    regimes = sorted({str((r.get("base") or {}).get("regime") or "UNKNOWN").upper() for r in rows})
    regime_options = ["ANY"] + regimes
    probability_thresholds = (55.0, 60.0, 65.0)
    confidence_thresholds = (20.0, 40.0, 60.0)
    alignment_thresholds = (0, 3, 5)
    agreement_options = ("ANY", "AGREE")
    results: List[Dict[str, Any]] = []

    for hours in (4, 8):
        for direction in ("BULLISH", "BEARISH"):
            prob_field = "bullish_probability" if direction == "BULLISH" else "bearish_probability"
            for pthr in probability_thresholds:
                for cthr in confidence_thresholds:
                    for athr in alignment_thresholds:
                        for regime in regime_options:
                            for agreement in agreement_options:
                                ids: List[str] = []
                                correct = 0
                                for row in rows:
                                    actual = _actual(row, hours)
                                    if actual not in {"BULLISH", "BEARISH"}:
                                        continue
                                    f = extract_lock_time_features(row, hours)
                                    pval = _float(f.get(prob_field))
                                    conf = _float(f.get("confidence"))
                                    align = int(f.get("component_alignment_count") or 0)
                                    if pval is None or conf is None or pval < pthr or conf < cthr or align < athr:
                                        continue
                                    if regime != "ANY" and f.get("regime") != regime:
                                        continue
                                    if agreement == "AGREE" and not f.get("horizon_agreement"):
                                        continue
                                    ids.append(str(row.get("forecast_id") or ""))
                                    correct += int(actual == direction)
                                n = len(ids)
                                pvalue = _binomial_upper_tail(correct, n) if n >= min_n else 1.0
                                results.append({
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
                                    "p_value_vs_50pct": pvalue,
                                    "eligible_min_n": n >= min_n,
                                    "discovery_forecast_ids": ids,
                                })
    qvalues = _bh_qvalues([float(r["p_value_vs_50pct"]) for r in results])
    for result, q in zip(results, qvalues):
        result["bh_q_value"] = q
        result["status"] = "EXPLORATORY_ONLY_NOT_PROVEN"
    return {
        "schema_version": LAB_SCHEMA_VERSION,
        "method": "PREDECLARED_CAUSAL_FEATURE_GRID_V1",
        "search_space": {
            "probability_thresholds": list(probability_thresholds),
            "confidence_thresholds": list(confidence_thresholds),
            "alignment_thresholds": list(alignment_thresholds),
            "regimes": regime_options,
            "agreement_options": list(agreement_options),
            "horizons": [4, 8],
            "directions": ["BULLISH", "BEARISH"],
        },
        "tests_run": len(results),
        "min_n": min_n,
        "multiple_testing_control": "BENJAMINI_HOCHBERG_REPORTED",
        "automatic_candidate_selection": False,
        "results": results,
        "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
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
        pvalue = _binomial_upper_tail(majority, n) if n >= min_n else 1.0
        items.append({
            "transition": transition,
            **bucket,
            "majority_direction": "BULLISH" if bucket["bullish"] > bucket["bearish"] else "BEARISH" if bucket["bearish"] > bucket["bullish"] else "TIE",
            "p_value_majority_vs_50pct": pvalue,
            "eligible_min_n": n >= min_n,
            "status": "EXPLORATORY_ONLY_NOT_PROVEN",
        })
    qvalues = _bh_qvalues([float(i["p_value_majority_vs_50pct"]) for i in items])
    for item, q in zip(items, qvalues):
        item["bh_q_value"] = q
    return {
        "horizon_hours": hours,
        "transitions": items,
        "automatic_candidate_generation": False,
        "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
    }
