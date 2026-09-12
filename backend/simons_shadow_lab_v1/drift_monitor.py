"""Permutation-calibrated decay/drift diagnostics for Shadow Lab V2.

A fixed threshold on a binary series can label almost everything as degrading.
This module instead compares the strongest early/late mean split to a shuffled
null. It is a research diagnostic only and never auto-deploys or modifies FIA.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence, Tuple


def _max_split_stat(values: Sequence[float], min_segment: int) -> Tuple[float, int | None]:
    vals = [float(v) for v in values]
    n = len(vals)
    if n < 2 * min_segment:
        return 0.0, None
    best, best_cut = 0.0, None
    prefix = [0.0]
    for v in vals:
        prefix.append(prefix[-1] + v)
    for cut in range(min_segment, n - min_segment + 1):
        left = prefix[cut] / cut
        right = (prefix[n] - prefix[cut]) / (n - cut)
        stat = abs(right - left)
        if stat > best:
            best, best_cut = stat, cut
    return best, best_cut


def permutation_drift_report(
    values: Sequence[float],
    permutations: int = 500,
    alpha: float = 0.01,
    min_segment: int = 10,
    seed: int = 20260911,
) -> Dict[str, Any]:
    clean = [float(v) for v in values]
    n = len(clean)
    if n < 2 * int(min_segment):
        return {
            "n": n,
            "assessed": False,
            "status": "INSUFFICIENT_SAMPLE_NOT_PROVEN",
            "p_value": None,
            "observed_max_mean_shift": None,
            "cut_index": None,
            "permutations": int(permutations),
            "alpha": float(alpha),
        }
    observed, cut = _max_split_stat(clean, int(min_segment))
    rng = random.Random(int(seed))
    null_stats: List[float] = []
    for _ in range(int(permutations)):
        perm = list(clean)
        rng.shuffle(perm)
        stat, _ = _max_split_stat(perm, int(min_segment))
        null_stats.append(stat)
    ge = sum(1 for stat in null_stats if stat >= observed)
    p = (ge + 1.0) / (len(null_stats) + 1.0)
    left_mean = sum(clean[:cut]) / cut if cut else None
    right_mean = sum(clean[cut:]) / (n - cut) if cut else None
    degrading = bool(p <= float(alpha) and left_mean is not None and right_mean is not None and right_mean < left_mean)
    return {
        "n": n,
        "assessed": True,
        "method": "PERMUTATION_CALIBRATED_MAX_MEAN_SHIFT_V1",
        "observed_max_mean_shift": observed,
        "cut_index": cut,
        "left_mean": left_mean,
        "right_mean": right_mean,
        "p_value": p,
        "permutations": int(permutations),
        "alpha": float(alpha),
        "degrading": degrading,
        "status": "DEGRADING_NOT_PROVEN" if degrading else "NO_SIGNIFICANT_DECAY_DETECTED_NOT_PROVEN",
    }
