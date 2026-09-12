from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math
import random
from typing import Dict, Hashable, Mapping, Optional, Sequence, Tuple

from .information import conditional_mutual_information, mutual_information


MIN_SAMPLES_PER_CELL = 10.0
MAX_FEATURES_FOR_NULL = 4
DEFAULT_NULL_PERMUTATIONS = 200


@dataclass(frozen=True)
class MarginalInformationResult:
    """Exact Shapley enumeration over a BIASED plug-in MI estimator.

    The enumeration is exact. The value function is not: plug-in mutual
    information saturates as the joint alphabet grows, and the audit showed six
    independent NOISE features reporting 0.78 bits of a maximum 0.99 -- roughly
    79% of the target's entropy attributed to noise. Attribution from this
    function is therefore never evidence on its own. Use
    shapley_information_evidence() for a null-calibrated screen.

    A correction to the audit is recorded here: it predicted the max(0.0, ...)
    clamp would break the Shapley efficiency axiom. Direct testing disproved
    that -- plug-in MI is monotone under feature addition, so the clamp never
    binds and efficiency held exactly. The defect is estimator bias, not the
    decomposition.
    """

    shapley_bits: Mapping[str, float]
    total_joint_information_bits: float
    feature_count: int
    samples: int = 0
    joint_cells: int = 0
    samples_per_cell: float = 0.0
    sample_adequate: bool = False
    calibrated: bool = False
    promotion_eligible: bool = False
    method: str = "EXACT_SHAPLEY_ENUMERATION_OVER_BIASED_PLUGIN_MI"


def _joint_feature(features: Mapping[str, Sequence[Hashable]], names: Sequence[str]) -> list[Hashable]:
    if not names:
        n = len(next(iter(features.values()))) if features else 0
        return [()] * n
    return [tuple(features[name][i] for name in names) for i in range(len(features[names[0]]))]


def incremental_information(
    candidate: Sequence[Hashable],
    target: Sequence[Hashable],
    conditioning: Sequence[Hashable] | None = None,
) -> float:
    if conditioning is None:
        return mutual_information(candidate, target)
    return conditional_mutual_information(candidate, target, conditioning)


def shapley_information(
    features: Mapping[str, Sequence[Hashable]],
    target: Sequence[Hashable],
    *,
    max_features: int = 8,
) -> MarginalInformationResult:
    names = tuple(sorted(features))
    m = len(names)
    if m == 0:
        return MarginalInformationResult({}, 0.0, 0)
    if m > max_features:
        raise ValueError("too many features for exact Shapley information; reduce/freeze feature set")
    n = len(target)
    if any(len(features[name]) != n for name in names):
        raise ValueError("all feature series and target must have equal length")
    joint_all = _joint_feature(features, names)
    total_joint = mutual_information(joint_all, target)
    out: Dict[str, float] = {name: 0.0 for name in names}
    factorial = math.factorial
    denom = factorial(m)
    for feature in names:
        others = tuple(x for x in names if x != feature)
        for r in range(len(others) + 1):
            weight = factorial(r) * factorial(m - r - 1) / denom
            for subset in combinations(others, r):
                before = 0.0 if not subset else mutual_information(_joint_feature(features, subset), target)
                after_names = tuple(sorted(subset + (feature,)))
                after = mutual_information(_joint_feature(features, after_names), target)
                out[feature] += weight * max(0.0, after - before)
    joint_cells = max(1, len(set(map(tuple, (tuple(v) for v in zip(*(features[x] for x in names)))))) if names else 1)
    alphabet_cells = 1
    for name in names:
        alphabet_cells *= max(1, len(set(features[name])))
    alphabet_cells *= max(1, len(set(target)))
    per_cell = n / alphabet_cells if alphabet_cells else 0.0
    return MarginalInformationResult(
        out, total_joint, m,
        samples=n, joint_cells=alphabet_cells, samples_per_cell=per_cell,
        sample_adequate=per_cell >= MIN_SAMPLES_PER_CELL)


@dataclass(frozen=True)
class MarginalInformationEvidence:
    raw: MarginalInformationResult
    null_mean_total: Optional[float]
    excess_total: Optional[float]
    p_value_total: Optional[float]
    per_feature_excess: Mapping[str, float]
    permutations: int
    status: str
    calibrated: bool = False
    promotion_eligible: bool = False


def shapley_information_evidence(
    features: Mapping[str, Sequence[Hashable]],
    target: Sequence[Hashable],
    *,
    permutations: int = DEFAULT_NULL_PERMUTATIONS,
    alpha: float = 0.01,
    seed: int = 20260912,
    max_features: int = MAX_FEATURES_FOR_NULL,
) -> MarginalInformationEvidence:
    """Shapley attribution screened against a permuted-target null.

    Shuffling the target destroys every feature-target relationship while
    preserving each feature's own marginal structure, so the null answers
    exactly the right question: how much attribution does this feature set
    produce when it carries no information at all?
    """
    smallest = 1.0 / (permutations + 1.0)
    if smallest > alpha:
        raise ValueError(
            f"{permutations} permutations cannot resolve alpha={alpha}; "
            f"smallest attainable p-value is {smallest:.4g}.")
    raw = shapley_information(features, target, max_features=max_features)
    names = tuple(sorted(features))
    if not names:
        return MarginalInformationEvidence(
            raw, None, None, None, {}, 0, "NOT_IDENTIFIABLE_WITH_CURRENT_DATA")
    if not raw.sample_adequate:
        return MarginalInformationEvidence(
            raw, None, None, None, {}, 0, "INSUFFICIENT_SAMPLE")

    rng = random.Random(seed)
    shuffled_target = list(target)
    totals = []
    per_feature: Dict[str, list] = {n: [] for n in names}
    for _ in range(permutations):
        rng.shuffle(shuffled_target)
        null = shapley_information(features, shuffled_target, max_features=max_features)
        totals.append(null.total_joint_information_bits)
        for name in names:
            per_feature[name].append(null.shapley_bits[name])

    at_least = sum(1 for v in totals if v >= raw.total_joint_information_bits - 1e-15)
    p_total = (1.0 + at_least) / (1.0 + len(totals))
    null_mean = sum(totals) / len(totals)
    excess = {n: raw.shapley_bits[n] - (sum(v) / len(v)) for n, v in per_feature.items()}
    status = ("SIGNIFICANT_UNCALIBRATED" if p_total <= alpha else "NOT_SIGNIFICANT")
    return MarginalInformationEvidence(
        raw=raw,
        null_mean_total=null_mean,
        excess_total=raw.total_joint_information_bits - null_mean,
        p_value_total=p_total,
        per_feature_excess=excess,
        permutations=permutations,
        status=status,
    )
