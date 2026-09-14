"""Scientific statistics for SIMONS SHADOW LAB V2 hybrid.

Adds the strongest anti-overfitting machinery from the independent Cloud build
without changing production logic: whole-grid multiplicity accounting,
Bonferroni + Benjamini-Hochberg reporting, Wilson intervals, power/sample-size
context, and a deterministic search-wide permutation null.
"""
from __future__ import annotations

import math
import random
from statistics import NormalDist
from typing import Any, Dict, List, Mapping, Sequence, Tuple


def binomial_upper_tail(k: int, n: int, p: float = 0.5) -> float:
    if n <= 0 or k < 0 or k > n or not (0.0 <= p <= 1.0):
        return 1.0
    return min(1.0, sum(math.comb(n, i) * p**i * (1.0 - p) ** (n - i) for i in range(k, n + 1)))


def bh_qvalues(pvalues: Sequence[float]) -> List[float]:
    m = len(pvalues)
    if not m:
        return []
    order = sorted(enumerate(pvalues), key=lambda pair: pair[1])
    out = [1.0] * m
    running = 1.0
    for rank_from_zero in range(m - 1, -1, -1):
        idx, p = order[rank_from_zero]
        running = min(running, float(p) * m / (rank_from_zero + 1))
        out[idx] = min(1.0, running)
    return out


def bonferroni(p: float, tests: int) -> float:
    return min(1.0, max(0.0, float(p)) * max(1, int(tests)))


def wilson_interval(k: int, n: int, confidence: float = 0.95) -> Tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    alpha = 1.0 - confidence
    z = NormalDist().inv_cdf(1.0 - alpha / 2.0)
    phat = k / n
    denom = 1.0 + z * z / n
    centre = (phat + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(phat * (1.0 - phat) / n + z * z / (4.0 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def required_sample_for_rate_difference(
    baseline: float = 0.5,
    target: float = 0.58,
    alpha: float = 0.05,
    power: float = 0.80,
) -> int:
    """Approximate one-sample proportion sample floor using normal power.

    This is planning context, not proof. It prevents fixed 30/50 row thresholds
    from being mistaken for universally adequate statistical power.
    """
    if not (0 < baseline < 1 and 0 < target < 1 and target != baseline):
        raise ValueError("baseline/target must be distinct probabilities in (0,1)")
    if not (0 < alpha < 1 and 0 < power < 1):
        raise ValueError("alpha/power must be in (0,1)")
    z_alpha = NormalDist().inv_cdf(1.0 - alpha / 2.0)
    z_power = NormalDist().inv_cdf(power)
    delta = abs(target - baseline)
    numerator = (
        z_alpha * math.sqrt(baseline * (1.0 - baseline))
        + z_power * math.sqrt(target * (1.0 - target))
    ) ** 2
    return max(1, int(math.ceil(numerator / (delta * delta))))


def _percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    vals = sorted(float(v) for v in values)
    if len(vals) == 1:
        return vals[0]
    x = (len(vals) - 1) * min(1.0, max(0.0, q))
    lo = int(math.floor(x)); hi = int(math.ceil(x))
    if lo == hi:
        return vals[lo]
    w = x - lo
    return vals[lo] * (1.0 - w) + vals[hi] * w


def search_wide_permutation_null(
    outcomes_by_horizon: Mapping[int, Sequence[str]],
    rule_masks: Sequence[Mapping[str, Any]],
    permutations: int = 200,
    seed: int = 20260911,
    min_n: int = 12,
) -> Dict[str, Any]:
    """Estimate the best-by-chance hit rate across the *entire* declared search.

    ``rule_masks`` entries contain horizon_hours, predicted_direction and a list
    of selected integer row indexes. Selection masks stay fixed while outcomes
    are shuffled within horizon; this prices the fact that many rules were tried.
    """
    if permutations < 1:
        raise ValueError("permutations must be >= 1")
    rng = random.Random(int(seed))
    normalized = {int(h): [str(x).upper() for x in vals] for h, vals in outcomes_by_horizon.items()}
    maxima: List[float] = []
    for _ in range(int(permutations)):
        shuffled = {h: list(vals) for h, vals in normalized.items()}
        for vals in shuffled.values():
            rng.shuffle(vals)
        best = 0.0
        for rule in rule_masks:
            h = int(rule.get("horizon_hours") or 0)
            direction = str(rule.get("predicted_direction") or "").upper()
            idxs = list(rule.get("selected_indexes") or [])
            if len(idxs) < int(min_n) or h not in shuffled or direction not in {"BULLISH", "BEARISH"}:
                continue
            ys = shuffled[h]
            valid = [i for i in idxs if 0 <= int(i) < len(ys) and ys[int(i)] in {"BULLISH", "BEARISH"}]
            if len(valid) < int(min_n):
                continue
            hit = sum(1 for i in valid if ys[int(i)] == direction) / len(valid)
            if hit > best:
                best = hit
        maxima.append(best)
    return {
        "method": "SEARCH_WIDE_PERMUTATION_NULL_V1",
        "permutations": int(permutations),
        "seed": int(seed),
        "min_n": int(min_n),
        "best_by_chance_mean_hit_rate": sum(maxima) / len(maxima) if maxima else None,
        "best_by_chance_p95_hit_rate": _percentile(maxima, 0.95),
        "best_by_chance_p99_hit_rate": _percentile(maxima, 0.99),
        "maxima": maxima,
        "warning": "Permutation null is discovery control, not untouched forward validation.",
    }
