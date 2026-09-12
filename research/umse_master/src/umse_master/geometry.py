"""Information geometry for regime-shift diagnostics.

WHAT THE AUDIT PROVED
---------------------
Two defects, both of the same family as the irreversibility one:

  * `_normalize` floored every probability at a raw 1e-12. A KL against a
    distribution with a true zero therefore contributed ~log(1e12) per bin, so
    the reported divergence was set by the floor constant rather than by the
    data -- the same artifact that made path irreversibility swing from 14.8 to
    35.5 on the choice of epsilon alone.
  * `wasserstein_1d_discrete` computes sum|CDF_p - CDF_q|, which is correct ONLY
    for a histogram on an ORDERED support. It was reachable with categorical
    inputs such as market-state or mechanism probability vectors, where no
    metric on the support exists and the number is meaningless.

REPAIR
------
Smoothing is a Dirichlet prior, (p + a) / (1 + a*K), so the statistic stays
comparable. Wasserstein requires the caller to assert `ordered_support=True`
and returns None otherwise, so a categorical distribution can no longer be
silently handed a metric it does not have. `jensen_shannon_bits` is added as
the bounded, symmetric primary statistic.

Nothing here is calibrated, and divergence magnitudes remain sensitive to
binning by nature -- the hypothesis registry already carries the kill rule
"Reject if divergence measures duplicate simpler regime statistics or are
unstable to binning".
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Sequence

DEFAULT_SMOOTHING = 0.5      # Jeffreys prior


def _normalize(values: Sequence[float], smoothing: float = DEFAULT_SMOOTHING) -> list[float]:
    xs = [max(0.0, float(x)) for x in values]
    total = sum(xs)
    if total <= 0:
        raise ValueError("distribution must have positive mass")
    if smoothing <= 0:
        raise ValueError("smoothing must be > 0")
    k = len(xs)
    # Dirichlet posterior mean over k categories, rather than a raw floor.
    return [(x / total + smoothing) / (1.0 + smoothing * k) for x in xs]


def kl_divergence(p: Sequence[float], q: Sequence[float],
                  smoothing: float = DEFAULT_SMOOTHING) -> float:
    """KL(p||q) in nats. Smoothing-dependent; prefer jensen_shannon_bits."""
    if len(p) != len(q) or not p:
        raise ValueError("p and q must have same nonzero length")
    pp, qq = _normalize(p, smoothing), _normalize(q, smoothing)
    return sum(a * math.log(a / b) for a, b in zip(pp, qq))


def jensen_shannon_divergence(p: Sequence[float], q: Sequence[float],
                              smoothing: float = DEFAULT_SMOOTHING) -> float:
    """JS divergence in NATS, bounded by ln 2."""
    pp, qq = _normalize(p, smoothing), _normalize(q, smoothing)
    m = [(a + b) / 2.0 for a, b in zip(pp, qq)]
    left = sum(a * math.log(a / c) for a, c in zip(pp, m))
    right = sum(b * math.log(b / c) for b, c in zip(qq, m))
    return max(0.0, 0.5 * left + 0.5 * right)


def jensen_shannon_bits(p: Sequence[float], q: Sequence[float],
                        smoothing: float = DEFAULT_SMOOTHING) -> float:
    """JS divergence in BITS, bounded in [0, 1]. The primary shift statistic."""
    return max(0.0, min(1.0, jensen_shannon_divergence(p, q, smoothing) / math.log(2.0)))


def wasserstein_1d_discrete(
    p: Sequence[float],
    q: Sequence[float],
    bin_width: float = 1.0,
    *,
    ordered_support: bool = False,
) -> Optional[float]:
    """1-D W1 between two histograms on an EQUALLY SPACED ORDERED support.

    Returns None unless the caller asserts `ordered_support=True`. The CDF
    formula below presumes the bins are ordered and adjacent; applied to a
    categorical distribution such as market-state probabilities it produces a
    number with no meaning, which is exactly what the audit found reachable.
    """
    if len(p) != len(q) or not p:
        raise ValueError("p and q must have same nonzero length")
    if not ordered_support:
        return None
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
    jensen_shannon_bits: float
    wasserstein: Optional[float]
    ordered_support: bool
    smoothing: float
    calibrated: bool = False
    predictive: bool = False


def distribution_shift(
    p: Sequence[float],
    q: Sequence[float],
    bin_width: float = 1.0,
    *,
    ordered_support: bool = False,
    smoothing: float = DEFAULT_SMOOTHING,
) -> GeometryShift:
    return GeometryShift(
        kl_forward=kl_divergence(p, q, smoothing),
        kl_reverse=kl_divergence(q, p, smoothing),
        jensen_shannon=jensen_shannon_divergence(p, q, smoothing),
        jensen_shannon_bits=jensen_shannon_bits(p, q, smoothing),
        wasserstein=wasserstein_1d_discrete(p, q, bin_width,
                                            ordered_support=ordered_support),
        ordered_support=ordered_support,
        smoothing=smoothing,
        calibrated=False,
        predictive=False,
    )
