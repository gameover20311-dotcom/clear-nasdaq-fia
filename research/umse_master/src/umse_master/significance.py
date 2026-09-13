"""Fail-closed null/significance framework for the information estimators.

WHY THIS EXISTS
---------------
The Cloud AI hostile audit proved that the project's stated ultimate test,
I(UMSE_t; Y_future | FIA_t) > 0, was satisfied by pure independent noise in
100% of trials. Plug-in entropy estimators are positively biased in finite
samples, so the raw statistic is essentially always > 0 whether or not any
information is present.

Two corrections follow, and both matter.

First, a clarification the audit itself got slightly wrong: the `max(0.0, ...)`
clamp in information.py is NOT the defect. Plug-in conditional mutual
information is the CMI of the empirical distribution and is therefore
non-negative by construction; the clamp only absorbs floating point error. It
was verified over 3000 random trials that the unclamped estimator never went
below -4.5e-16. Removing the clamp would change nothing.

The real defect is that a raw positive number was treated as evidence with no
reference distribution. This module supplies that reference distribution.

THE NULL
--------
For a conditional test the correct null is conditional independence, not total
independence. Shuffling X wholesale would also destroy the X-Z relationship and
produce an inappropriately easy null. Instead X is permuted WITHIN each stratum
of Z, which preserves p(x|z) and p(y|z) exactly while enforcing
X ⟂ Y | Z. That is the standard conditional permutation test.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not calibrate anything, and it does not make anything promotion
eligible. `calibrated` and `promotion_eligible` are hardcoded False on every
result. A significant result here means only "larger than its own conditional
permutation null on this sample", which is a screening outcome, never edge.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import random
from typing import Callable, Hashable, Optional, Sequence, Tuple

from .information import conditional_mutual_information, mutual_information

# A joint contingency table needs enough observations per cell before a
# plug-in estimate means anything at all. This is a structural floor on the
# estimator, not a fitted or power-derived quantity.
MIN_SAMPLES_PER_CELL = 10.0
DEFAULT_PERMUTATIONS = 200
DEFAULT_ALPHA = 0.01
DEFAULT_SEED = 20260912


class EvidenceStatus(str, Enum):
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    NOT_SIGNIFICANT = "NOT_SIGNIFICANT"
    SIGNIFICANT_UNCALIBRATED = "SIGNIFICANT_UNCALIBRATED"
    NOT_IDENTIFIABLE_WITH_CURRENT_DATA = "NOT_IDENTIFIABLE_WITH_CURRENT_DATA"


@dataclass(frozen=True)
class NullCalibratedEstimate:
    """A raw statistic and its evidence status, deliberately kept separate."""

    statistic: str
    raw_estimate: float
    null_mean: Optional[float]
    null_upper_quantile: Optional[float]
    excess_over_null: Optional[float]
    p_value: Optional[float]
    permutations: int
    samples: int
    cells: int
    samples_per_cell: float
    alpha: float
    status: EvidenceStatus
    # A null test is a screen. It is never calibration and never promotion
    # evidence, regardless of outcome.
    calibrated: bool = False
    promotion_eligible: bool = False

    @property
    def significant(self) -> bool:
        return self.status == EvidenceStatus.SIGNIFICANT_UNCALIBRATED


def _require_resolvable_alpha(permutations: int, alpha: float) -> None:
    """A permutation test cannot reject below its own resolution.

    The smallest attainable p-value is 1/(permutations+1). If that exceeds
    alpha the test can NEVER be significant, and would silently report
    NOT_SIGNIFICANT for even overwhelming dependence. Fail loudly instead.
    """
    if permutations < 1:
        raise ValueError("permutations must be >= 1")
    smallest = 1.0 / (permutations + 1.0)
    if smallest > alpha:
        raise ValueError(
            f"{permutations} permutations cannot resolve alpha={alpha}; "
            f"smallest attainable p-value is {smallest:.4g}. "
            f"Use at least {int(math.ceil(1.0 / alpha)) - 1} permutations.")


def _distinct(values: Sequence[Hashable]) -> int:
    return len(set(values))


def _stratified_shuffle(
    x: Sequence[Hashable], z: Sequence[Hashable], rng: random.Random
) -> list:
    """Permute x within each stratum of z.

    Enforces X ⟂ Y | Z while preserving the empirical p(x|z). A wholesale
    shuffle would also destroy the X-Z relationship, making the null easier to
    beat and the test anti-conservative.
    """
    buckets: dict = {}
    for i, zv in enumerate(z):
        buckets.setdefault(zv, []).append(i)
    out = list(x)
    for indices in buckets.values():
        values = [x[i] for i in indices]
        rng.shuffle(values)
        for i, v in zip(indices, values):
            out[i] = v
    return out


def _permutation_outcome(
    statistic: str,
    raw: float,
    nulls: Sequence[float],
    samples: int,
    cells: int,
    alpha: float,
    permutations: int,
) -> NullCalibratedEstimate:
    ordered = sorted(nulls)
    n_null = len(ordered)
    # Conservative permutation p-value: the observed value is counted as one of
    # its own reference draws, so p can never be exactly zero.
    at_least = sum(1 for v in ordered if v >= raw - 1e-15)
    p_value = (1.0 + at_least) / (1.0 + n_null)
    null_mean = sum(ordered) / n_null
    idx = min(n_null - 1, int(math.ceil((1.0 - alpha) * n_null)) - 1)
    upper = ordered[max(0, idx)]
    status = (
        EvidenceStatus.SIGNIFICANT_UNCALIBRATED
        if p_value <= alpha
        else EvidenceStatus.NOT_SIGNIFICANT
    )
    return NullCalibratedEstimate(
        statistic=statistic,
        raw_estimate=raw,
        null_mean=null_mean,
        null_upper_quantile=upper,
        excess_over_null=raw - null_mean,
        p_value=p_value,
        permutations=permutations,
        samples=samples,
        cells=cells,
        samples_per_cell=samples / cells if cells else 0.0,
        alpha=alpha,
        status=status,
    )


def _insufficient(
    statistic: str, raw: float, samples: int, cells: int, alpha: float
) -> NullCalibratedEstimate:
    return NullCalibratedEstimate(
        statistic=statistic,
        raw_estimate=raw,
        null_mean=None,
        null_upper_quantile=None,
        excess_over_null=None,
        p_value=None,
        permutations=0,
        samples=samples,
        cells=cells,
        samples_per_cell=samples / cells if cells else 0.0,
        alpha=alpha,
        status=EvidenceStatus.INSUFFICIENT_SAMPLE,
    )


def conditional_information_evidence(
    x: Sequence[Hashable],
    y: Sequence[Hashable],
    z: Sequence[Hashable],
    *,
    permutations: int = DEFAULT_PERMUTATIONS,
    alpha: float = DEFAULT_ALPHA,
    seed: int = DEFAULT_SEED,
    min_samples_per_cell: float = MIN_SAMPLES_PER_CELL,
) -> NullCalibratedEstimate:
    """I(X;Y|Z) against its conditional permutation null."""
    if not (len(x) == len(y) == len(z)):
        raise ValueError("x, y and z must have equal length")
    _require_resolvable_alpha(permutations, alpha)
    n = len(x)
    raw = conditional_mutual_information(x, y, z) if n else 0.0
    cells = max(1, _distinct(x) * _distinct(y) * _distinct(z))
    if n == 0 or n / cells < min_samples_per_cell:
        return _insufficient("conditional_mutual_information", raw, n, cells, alpha)
    rng = random.Random(seed)
    nulls = [
        conditional_mutual_information(_stratified_shuffle(x, z, rng), y, z)
        for _ in range(permutations)
    ]
    return _permutation_outcome(
        "conditional_mutual_information", raw, nulls, n, cells, alpha, permutations
    )


def mutual_information_evidence(
    x: Sequence[Hashable],
    y: Sequence[Hashable],
    *,
    permutations: int = DEFAULT_PERMUTATIONS,
    alpha: float = DEFAULT_ALPHA,
    seed: int = DEFAULT_SEED,
    min_samples_per_cell: float = MIN_SAMPLES_PER_CELL,
) -> NullCalibratedEstimate:
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    _require_resolvable_alpha(permutations, alpha)
    n = len(x)
    raw = mutual_information(x, y) if n else 0.0
    cells = max(1, _distinct(x) * _distinct(y))
    if n == 0 or n / cells < min_samples_per_cell:
        return _insufficient("mutual_information", raw, n, cells, alpha)
    rng = random.Random(seed)
    constant = [0] * n
    nulls = [
        mutual_information(_stratified_shuffle(x, constant, rng), y)
        for _ in range(permutations)
    ]
    return _permutation_outcome(
        "mutual_information", raw, nulls, n, cells, alpha, permutations
    )


def transfer_entropy_evidence(
    source: Sequence[Hashable],
    target: Sequence[Hashable],
    *,
    lag: int = 1,
    permutations: int = DEFAULT_PERMUTATIONS,
    alpha: float = DEFAULT_ALPHA,
    seed: int = DEFAULT_SEED,
    min_samples_per_cell: float = MIN_SAMPLES_PER_CELL,
) -> NullCalibratedEstimate:
    """TE = I(source_past ; target_future | target_past), against its null.

    The null permutes source_past within strata of target_past, so the target's
    own autocorrelation is preserved and cannot masquerade as transfer.
    """
    if len(source) != len(target):
        raise ValueError("source and target must have equal length")
    if lag <= 0 or len(source) <= lag:
        return _insufficient("transfer_entropy", 0.0, len(source), 1, alpha)
    x_past = list(source[:-lag])
    y_future = list(target[lag:])
    y_past = list(target[:-lag])
    return conditional_information_evidence(
        x_past, y_future, y_past,
        permutations=permutations, alpha=alpha, seed=seed,
        min_samples_per_cell=min_samples_per_cell,
    )


def incremental_information_evidence(
    umse_series: Sequence[Hashable],
    future_series: Sequence[Hashable],
    fia_series: Sequence[Hashable],
    *,
    permutations: int = DEFAULT_PERMUTATIONS,
    alpha: float = DEFAULT_ALPHA,
    seed: int = DEFAULT_SEED,
) -> NullCalibratedEstimate:
    """The project's stated ultimate test, I(UMSE;Y_future|FIA), null-calibrated.

    A positive raw estimate is NOT the criterion and never was a valid one.
    The criterion is `status == SIGNIFICANT_UNCALIBRATED`, and even that is a
    screening result: `promotion_eligible` remains False. Promotion runs
    through the preregistered confirmatory gate in validation.py, on forward
    out-of-sample observations, and nowhere else.
    """
    return conditional_information_evidence(
        umse_series, future_series, fia_series,
        permutations=permutations, alpha=alpha, seed=seed,
    )
