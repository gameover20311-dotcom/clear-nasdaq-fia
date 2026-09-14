"""Negative controls for Shadow Lab V2 Hybrid.

The harness deliberately destroys the relationship between lock-time features
and future outcomes while preserving each horizon's resolved-label count,
class balance, missingness pattern and all lock-time features.  The same
predeclared discovery machinery is then re-run.  If scrambled labels repeatedly
produce 'robust' discoveries, the research pipeline is not trustworthy.

Negative controls are a pipeline diagnostic.  Passing them does not prove a
real NQ edge; failing them blocks scientific promotion until the defect is
understood.
"""
from __future__ import annotations

import copy
import random
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .causal_features import extract_lock_time_features
from .scientific_stats import wilson_interval

_VALID_DIRECTIONS = {"BULLISH", "BEARISH"}


def _resolved_direction(row: Mapping[str, Any], hours: int) -> str:
    return str(((row.get("outcomes") or {}).get(f"{hours}h") or {}).get("actual_direction") or "").upper()


def resolved_counts(rows: Sequence[Mapping[str, Any]]) -> Dict[int, Dict[str, int]]:
    out: Dict[int, Dict[str, int]] = {}
    for hours in (4, 8):
        bull = bear = missing = 0
        for row in rows:
            value = _resolved_direction(row, hours)
            if value == "BULLISH":
                bull += 1
            elif value == "BEARISH":
                bear += 1
            else:
                missing += 1
        out[hours] = {
            "resolved": bull + bear,
            "bullish": bull,
            "bearish": bear,
            "missing_or_unresolved": missing,
        }
    return out


def scramble_outcome_directions(
    rows: Sequence[Mapping[str, Any]],
    seed: int,
) -> List[Dict[str, Any]]:
    """Shuffle resolved direction labels within each horizon only.

    This preserves the exact marginal bullish/bearish counts and unresolved-row
    locations.  No lock-time field is modified.
    """
    cloned: List[Dict[str, Any]] = copy.deepcopy([dict(r) for r in rows])
    for hours in (4, 8):
        indexes: List[int] = []
        labels: List[str] = []
        for i, row in enumerate(cloned):
            label = _resolved_direction(row, hours)
            if label in _VALID_DIRECTIONS:
                indexes.append(i)
                labels.append(label)
        rng = random.Random(int(seed) * 1009 + hours * 7919)
        rng.shuffle(labels)
        for idx, label in zip(indexes, labels):
            outcome = ((cloned[idx].get("outcomes") or {}).get(f"{hours}h") or {})
            outcome["actual_direction"] = label
    return cloned


def lock_time_feature_invariance(
    original: Sequence[Mapping[str, Any]],
    scrambled: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    if len(original) != len(scrambled):
        return {"ok": False, "reason": "row_count_changed"}
    mismatches: List[str] = []
    for a, b in zip(original, scrambled):
        for hours in (4, 8):
            try:
                fa = extract_lock_time_features(a, hours)
                fb = extract_lock_time_features(b, hours)
            except Exception as exc:
                mismatches.append(f"feature_error:{hours}:{type(exc).__name__}")
                continue
            if fa != fb:
                mismatches.append(f"feature_changed:{a.get('forecast_id')}:{hours}h")
    return {
        "ok": not mismatches,
        "mismatches": mismatches,
        "rows_checked": len(original),
        "horizons_checked": [4, 8],
    }


def run_negative_control_harness(
    rows: Sequence[Dict[str, Any]],
    *,
    trials: int = 100,
    min_n: int = 12,
    discovery_permutations: int = 100,
    alpha: float = 0.05,
    seed: int = 20260911,
    max_tests: int = 10000,
    search_runner: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run the real discovery pipeline on repeatedly scrambled outcomes.

    The primary diagnostic is the fraction of scrambled trials in which the
    pipeline still reports at least one ``robust_discovery_screen`` survivor.
    A PASS requires >=100 trials and the 95% Wilson upper bound of that false
    discovery trial-rate to be <= ``alpha``.  This is deliberately strict.
    """
    if int(trials) < 1:
        raise ValueError("trials must be >= 1")
    if int(min_n) < 1:
        raise ValueError("min_n must be >= 1")
    if int(discovery_permutations) < 1:
        raise ValueError("discovery_permutations must be >= 1")
    if not (0.0 < float(alpha) < 1.0):
        raise ValueError("alpha must be in (0,1)")

    counts_before = resolved_counts(rows)
    eligible_horizons = [h for h, c in counts_before.items() if int(c["resolved"]) >= int(min_n)]
    if not eligible_horizons:
        return {
            "method": "SCRAMBLED_LABEL_NEGATIVE_CONTROL_V1",
            "status": "INSUFFICIENT_REAL_RESOLUTIONS",
            "eligible_horizons": [],
            "resolved_counts": counts_before,
            "trials_requested": int(trials),
            "trials_run": 0,
            "negative_control_pass": False,
            "gate_evaluable": False,
            "predictive_edge_proven": False,
            "production_modified": False,
            "reason": f"No horizon has min_n={int(min_n)} resolved observations.",
        }

    if search_runner is None:
        from .causal_discovery import discover_causal_grid
        search_runner = discover_causal_grid

    false_positive_trials = 0
    total_survivors = 0
    per_trial: List[Dict[str, Any]] = []
    invariance_ok = True
    for trial in range(int(trials)):
        trial_seed = int(seed) + trial * 104729
        scrambled = scramble_outcome_directions(rows, trial_seed)
        if resolved_counts(scrambled) != counts_before:
            raise RuntimeError("negative control failed to preserve resolved label marginals")
        invariance = lock_time_feature_invariance(rows, scrambled)
        if not invariance["ok"]:
            invariance_ok = False
            raise RuntimeError("negative control modified lock-time features")
        result = search_runner(
            scrambled,
            min_n=int(min_n),
            permutations=int(discovery_permutations),
            permutation_seed=trial_seed + 17,
            max_tests=int(max_tests),
        )
        survivors = [r for r in (result.get("results") or []) if bool(r.get("robust_discovery_screen"))]
        if survivors:
            false_positive_trials += 1
            total_survivors += len(survivors)
        min_search_p = min(
            [float(r["search_wide_permutation_p_value"]) for r in (result.get("results") or [])
             if r.get("search_wide_permutation_p_value") is not None],
            default=None,
        )
        per_trial.append({
            "trial": trial + 1,
            "seed": trial_seed,
            "robust_survivors": len(survivors),
            "minimum_search_wide_p": min_search_p,
        })

    rate = false_positive_trials / int(trials)
    low, high = wilson_interval(false_positive_trials, int(trials))
    gate_evaluable = int(trials) >= 100
    if gate_evaluable and high is not None and high <= float(alpha):
        status = "PASS_NEGATIVE_CONTROL"
        passed = True
    elif rate > float(alpha):
        status = "FAIL_NEGATIVE_CONTROL_FALSE_DISCOVERY_RATE_TOO_HIGH"
        passed = False
    else:
        status = "INCONCLUSIVE_NEGATIVE_CONTROL_MORE_TRIALS_REQUIRED"
        passed = False

    return {
        "method": "SCRAMBLED_LABEL_NEGATIVE_CONTROL_V1",
        "status": status,
        "eligible_horizons": eligible_horizons,
        "resolved_counts": counts_before,
        "trials_requested": int(trials),
        "trials_run": int(trials),
        "discovery_permutations_per_trial": int(discovery_permutations),
        "alpha": float(alpha),
        "false_positive_trials": false_positive_trials,
        "false_positive_trial_rate": rate,
        "false_positive_trial_rate_wilson_95": [low, high],
        "total_robust_survivors_across_controls": total_survivors,
        "lock_time_feature_invariance_verified": invariance_ok,
        "marginal_label_counts_preserved": True,
        "gate_evaluable": gate_evaluable,
        "negative_control_pass": passed,
        "automatic_production_promotion": False,
        "predictive_edge_proven": False,
        "production_modified": False,
        "trial_summaries": per_trial,
        "warning": (
            "A clean negative control is necessary but not sufficient. It validates the research pipeline, "
            "not the existence of a real predictive edge."
        ),
    }
