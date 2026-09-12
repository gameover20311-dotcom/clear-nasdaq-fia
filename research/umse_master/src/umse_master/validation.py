from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Dict, Iterable, Mapping, Sequence, Tuple


CLASSES = ("bullish", "bearish", "neutral")


def _probs(row: Mapping[str, float]) -> Dict[str, float]:
    vals = {k: float(row.get(k, 0.0)) for k in CLASSES}
    if any(not math.isfinite(v) or v < 0 for v in vals.values()):
        raise ValueError("invalid probability")
    total = sum(vals.values())
    if total <= 0:
        raise ValueError("probabilities require positive mass")
    return {k: v / total for k, v in vals.items()}


def multiclass_brier(probabilities: Mapping[str, float], outcome: str) -> float:
    if outcome not in CLASSES:
        raise ValueError(f"outcome must be one of {CLASSES}")
    p = _probs(probabilities)
    return sum((p[k] - (1.0 if k == outcome else 0.0)) ** 2 for k in CLASSES)


def paired_brier_differences(
    base: Sequence[Mapping[str, float]],
    candidate: Sequence[Mapping[str, float]],
    outcomes: Sequence[str],
) -> Tuple[float, ...]:
    if not (len(base) == len(candidate) == len(outcomes)):
        raise ValueError("base, candidate and outcomes must have equal length")
    return tuple(multiclass_brier(b, y) - multiclass_brier(c, y) for b, c, y in zip(base, candidate, outcomes))


def block_bootstrap_ci(
    values: Sequence[float],
    *,
    confidence: float = 0.90,
    block_size: int = 5,
    draws: int = 2000,
    seed: int = 56,
) -> tuple[float, float]:
    xs = [float(x) for x in values]
    if not xs:
        return (float("nan"), float("nan"))
    if block_size <= 0 or draws <= 0:
        raise ValueError("block_size and draws must be > 0")
    rng = random.Random(seed)
    n = len(xs)
    block_size = min(block_size, n)
    means = []
    for _ in range(draws):
        sample = []
        while len(sample) < n:
            start = rng.randrange(0, n - block_size + 1)
            sample.extend(xs[start : start + block_size])
        sample = sample[:n]
        means.append(sum(sample) / n)
    means.sort()
    alpha = (1.0 - confidence) / 2.0
    lo = means[int(alpha * (draws - 1))]
    hi = means[int((1.0 - alpha) * (draws - 1))]
    return lo, hi


def expected_calibration_error(
    probabilities: Sequence[Mapping[str, float]], outcomes: Sequence[str], bins: int = 10
) -> float:
    if len(probabilities) != len(outcomes):
        raise ValueError("length mismatch")
    if not probabilities:
        return float("nan")
    bucket_rows = [[] for _ in range(bins)]
    for p_raw, y in zip(probabilities, outcomes):
        p = _probs(p_raw)
        pred = max(CLASSES, key=lambda k: p[k])
        conf = p[pred]
        idx = min(bins - 1, int(conf * bins))
        bucket_rows[idx].append((conf, 1.0 if pred == y else 0.0))
    n = len(probabilities)
    ece = 0.0
    for rows in bucket_rows:
        if not rows:
            continue
        mean_conf = sum(x for x, _ in rows) / len(rows)
        accuracy = sum(y for _, y in rows) / len(rows)
        ece += len(rows) / n * abs(mean_conf - accuracy)
    return ece


@dataclass(frozen=True)
class PairedValidationResult:
    n: int
    base_mean_brier: float
    candidate_mean_brier: float
    mean_delta: float
    delta_ci90: tuple[float, float]
    base_ece: float
    candidate_ece: float
    target_delta: float
    confirmatory_eligible: bool
    promotion_gate_pass: bool
    note: str


def evaluate_paired_candidate(
    base: Sequence[Mapping[str, float]],
    candidate: Sequence[Mapping[str, float]],
    outcomes: Sequence[str],
    *,
    expected_n: int | None = None,
    target_delta: float = 0.010,
) -> PairedValidationResult:
    n = len(outcomes)
    if not (len(base) == len(candidate) == n):
        raise ValueError("length mismatch")
    if n == 0:
        return PairedValidationResult(0, math.nan, math.nan, math.nan, (math.nan, math.nan), math.nan, math.nan, target_delta, False, False, "NO_OBSERVATIONS")
    base_losses = [multiclass_brier(p, y) for p, y in zip(base, outcomes)]
    cand_losses = [multiclass_brier(p, y) for p, y in zip(candidate, outcomes)]
    diffs = [a - b for a, b in zip(base_losses, cand_losses)]
    ci = block_bootstrap_ci(diffs)
    exact_n = expected_n is not None and n == expected_n
    gate = exact_n and (sum(diffs) / n) >= target_delta and ci[0] > 0.0
    return PairedValidationResult(
        n=n,
        base_mean_brier=sum(base_losses) / n,
        candidate_mean_brier=sum(cand_losses) / n,
        mean_delta=sum(diffs) / n,
        delta_ci90=ci,
        base_ece=expected_calibration_error(base, outcomes),
        candidate_ece=expected_calibration_error(candidate, outcomes),
        target_delta=target_delta,
        confirmatory_eligible=exact_n,
        promotion_gate_pass=gate,
        note="FIXED_N_REQUIRED_NO_OPTIONAL_STOPPING" if expected_n is not None else "DIAGNOSTIC_ONLY_NO_FIXED_N",
    )
