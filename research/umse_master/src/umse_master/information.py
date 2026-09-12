from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Hashable, Iterable, Mapping, Sequence, Tuple


def _entropy_from_counts(counts: Counter) -> float:
    n = sum(counts.values())
    if n <= 0:
        return 0.0
    h = 0.0
    for count in counts.values():
        if count <= 0:
            continue
        p = count / n
        h -= p * math.log2(p)
    return h


def entropy(values: Sequence[Hashable]) -> float:
    return _entropy_from_counts(Counter(values))


def mutual_information(x: Sequence[Hashable], y: Sequence[Hashable]) -> float:
    if len(x) != len(y):
        raise ValueError("x and y must have equal length")
    if not x:
        return 0.0
    return entropy(x) + entropy(y) - entropy(list(zip(x, y)))


def conditional_mutual_information(
    x: Sequence[Hashable], y: Sequence[Hashable], z: Sequence[Hashable]
) -> float:
    if not (len(x) == len(y) == len(z)):
        raise ValueError("x, y and z must have equal length")
    if not x:
        return 0.0
    # I(X;Y|Z) = H(X,Z)+H(Y,Z)-H(Z)-H(X,Y,Z)
    return max(
        0.0,
        entropy(list(zip(x, z)))
        + entropy(list(zip(y, z)))
        - entropy(z)
        - entropy(list(zip(x, y, z))),
    )


def transfer_entropy(source: Sequence[Hashable], target: Sequence[Hashable], lag: int = 1) -> float:
    if len(source) != len(target):
        raise ValueError("source and target must have equal length")
    if lag <= 0 or len(source) <= lag:
        return 0.0
    x_past = list(source[:-lag])
    y_future = list(target[lag:])
    y_past = list(target[:-lag])
    return conditional_mutual_information(x_past, y_future, y_past)


@dataclass(frozen=True)
class PIDApproximation:
    unique_x: float
    unique_z: float
    redundancy: float
    synergy: float
    joint_information: float
    method: str = "I_MIN_STYLE_HEURISTIC_NOT_FULL_PID"


def pid_i_min_approximation(
    x: Sequence[Hashable], z: Sequence[Hashable], target: Sequence[Hashable]
) -> PIDApproximation:
    if not (len(x) == len(z) == len(target)):
        raise ValueError("inputs must have equal length")
    ix = mutual_information(x, target)
    iz = mutual_information(z, target)
    joint = mutual_information(list(zip(x, z)), target)
    redundancy = min(ix, iz)
    unique_x = max(0.0, ix - redundancy)
    unique_z = max(0.0, iz - redundancy)
    synergy = max(0.0, joint - unique_x - unique_z - redundancy)
    return PIDApproximation(unique_x, unique_z, redundancy, synergy, joint)


@dataclass(frozen=True)
class InformationEdge:
    source: str
    target: str
    transfer_entropy_bits: float
    conditional_information_bits: float
    calibrated: bool = False


def build_information_edge(
    source_name: str,
    target_name: str,
    source_series: Sequence[Hashable],
    target_series: Sequence[Hashable],
    conditioning_series: Sequence[Hashable] | None = None,
) -> InformationEdge:
    te = transfer_entropy(source_series, target_series)
    if conditioning_series is None:
        cmi = mutual_information(source_series, target_series)
    else:
        cmi = conditional_mutual_information(source_series, target_series, conditioning_series)
    return InformationEdge(source_name, target_name, te, cmi, False)
