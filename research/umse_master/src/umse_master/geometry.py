from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence


def _normalize(values: Sequence[float], epsilon: float = 1e-12) -> list[float]:
    xs = [max(0.0, float(x)) for x in values]
    total = sum(xs)
    if total <= 0:
        raise ValueError("distribution must have positive mass")
    probs = [max(epsilon, x / total) for x in xs]
    s = sum(probs)
    return [x / s for x in probs]


def kl_divergence(p: Sequence[float], q: Sequence[float]) -> float:
    if len(p) != len(q) or not p:
        raise ValueError("p and q must have same nonzero length")
    pp, qq = _normalize(p), _normalize(q)
    return sum(a * math.log(a / b) for a, b in zip(pp, qq))


def jensen_shannon_divergence(p: Sequence[float], q: Sequence[float]) -> float:
    pp, qq = _normalize(p), _normalize(q)
    m = [(a + b) / 2.0 for a, b in zip(pp, qq)]
    return 0.5 * kl_divergence(pp, m) + 0.5 * kl_divergence(qq, m)


def wasserstein_1d_discrete(p: Sequence[float], q: Sequence[float], bin_width: float = 1.0) -> float:
    if len(p) != len(q) or not p:
        raise ValueError("p and q must have same nonzero length")
    pp, qq = _normalize(p), _normalize(q)
    cp = cq = total = 0.0
    for a, b in zip(pp, qq):
        cp += a
        cq += b
        total += abs(cp - cq) * bin_width
    return total


@dataclass(frozen=True)
class GeometryShift:
    kl_forward: float
    kl_reverse: float
    jensen_shannon: float
    wasserstein: float
    calibrated: bool = False


def distribution_shift(p: Sequence[float], q: Sequence[float], bin_width: float = 1.0) -> GeometryShift:
    return GeometryShift(
        kl_forward=kl_divergence(p, q),
        kl_reverse=kl_divergence(q, p),
        jensen_shannon=jensen_shannon_divergence(p, q),
        wasserstein=wasserstein_1d_discrete(p, q, bin_width),
        calibrated=False,
    )
