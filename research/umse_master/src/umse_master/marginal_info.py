from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math
from typing import Dict, Hashable, Mapping, Sequence, Tuple

from .information import conditional_mutual_information, mutual_information


@dataclass(frozen=True)
class MarginalInformationResult:
    shapley_bits: Mapping[str, float]
    total_joint_information_bits: float
    feature_count: int
    method: str = "EXACT_SHAPLEY_OVER_EMPIRICAL_MUTUAL_INFORMATION"


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
    return MarginalInformationResult(out, total_joint, m)
