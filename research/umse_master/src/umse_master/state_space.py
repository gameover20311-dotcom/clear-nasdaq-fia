from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence, Tuple


def _normalize(values: Sequence[float]) -> tuple[float, ...]:
    xs = [float(x) for x in values]
    if any((not math.isfinite(x) or x < 0) for x in xs):
        raise ValueError("probabilities/likelihoods must be finite and >= 0")
    total = sum(xs)
    if total <= 0:
        raise ValueError("positive probability mass required")
    return tuple(x / total for x in xs)


@dataclass(frozen=True)
class FilterStep:
    posterior: Tuple[float, ...]
    predictive_prior: Tuple[float, ...]
    evidence_normalizer: float


@dataclass(frozen=True)
class HMMFilterResult:
    states: Tuple[str, ...]
    steps: Tuple[FilterStep, ...]
    learned_parameters: bool = False
    calibrated: bool = False


def forward_filter(
    *,
    states: Sequence[str],
    prior: Sequence[float],
    transition: Sequence[Sequence[float]],
    emission_likelihoods: Sequence[Sequence[float]],
) -> HMMFilterResult:
    names = tuple(str(s) for s in states)
    n = len(names)
    if n == 0 or len(prior) != n or len(transition) != n:
        raise ValueError("dimension mismatch")
    trans = []
    for row in transition:
        if len(row) != n:
            raise ValueError("transition matrix must be square")
        trans.append(_normalize(row))
    current = _normalize(prior)
    steps = []
    for emission in emission_likelihoods:
        if len(emission) != n:
            raise ValueError("emission likelihood dimension mismatch")
        predictive = tuple(sum(current[i] * trans[i][j] for i in range(n)) for j in range(n))
        unnormalized = [predictive[j] * float(emission[j]) for j in range(n)]
        z = sum(unnormalized)
        if z <= 0 or not math.isfinite(z):
            raise ValueError("observation has zero/invalid evidence under all states")
        current = tuple(x / z for x in unnormalized)
        steps.append(FilterStep(current, predictive, z))
    return HMMFilterResult(names, tuple(steps), learned_parameters=False, calibrated=False)
