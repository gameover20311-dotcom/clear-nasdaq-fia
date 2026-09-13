"""Path irreversibility with a bounded statistic and principled smoothing.

WHAT THE AUDIT PROVED
---------------------
The reported magnitude was a function of the `epsilon` constant, not of the
data. A raw additive epsilon on counts meant every unmatched transition
contributed roughly log(1/epsilon), so the same 9-step sequence returned:

    epsilon=1e-06 -> 14.81      epsilon=1e-12 -> 28.63
    epsilon=1e-09 -> 21.72      epsilon=1e-15 -> 35.54

An unbounded statistic that moves 2.4x on an arbitrary numerical constant
cannot be compared across runs or thresholded.

REPAIR
------
Two changes.

  * Smoothing is now a Dirichlet prior, (count + a) / (total + a*K), which is a
    proper posterior mean over K transition types rather than a raw floor. The
    statistic stays finite and comparable.
  * The primary statistic is the Jensen-Shannon divergence between the forward
    and reversed transition distributions, in bits. JS is symmetric, always
    finite, and bounded in [0, 1] bit, so a maximum is interpretable and
    smoothing cannot inflate it without limit. The KL is retained for
    continuity but is explicitly secondary.

A structural limitation is now reported rather than hidden: over a two-state
alphabet the forward and reverse transition counts are forced to near-equality,
so the measure is blind there. A perfectly alternating 400-step A/B sequence
returns exactly 0.0. Sequences with fewer than three distinct states are
marked `identifiable = False`.

This is a descriptive diagnostic. It is never calibrated predictive evidence.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Hashable, Sequence

DEFAULT_SMOOTHING = 0.5          # Jeffreys prior
MIN_DISTINCT_STATES = 3
# A Dirichlet prior is only negligible relative to the data once each
# transition type has been observed several times. Below this the statistic is
# genuinely prior-dominated -- that is a property of the sample, not a bug, and
# it is reported rather than smoothed over.
MIN_TRANSITIONS_PER_KEY = 5.0


@dataclass(frozen=True)
class IrreversibilityDiagnostics:
    forward_reverse_js: float        # primary, bounded in [0, 1] bit
    forward_reverse_kl: float        # secondary, smoothing dependent
    transition_entropy_bits: float
    unique_transitions: int
    distinct_states: int
    smoothing: float
    transitions_per_key: float
    identifiable: bool
    calibrated: bool = False
    predictive: bool = False


def _dirichlet(counts: Counter, keys, alpha: float) -> dict:
    total = sum(counts.get(k, 0) for k in keys)
    k = len(keys)
    denom = total + alpha * k
    if denom <= 0:
        return {key: 1.0 / k for key in keys}
    return {key: (counts.get(key, 0) + alpha) / denom for key in keys}


def _kl_bits(p: dict, q: dict) -> float:
    return sum(p[k] * math.log2(p[k] / q[k]) for k in p if p[k] > 0)


def path_irreversibility(
    states: Sequence[Hashable],
    smoothing: float = DEFAULT_SMOOTHING,
) -> IrreversibilityDiagnostics:
    if smoothing <= 0:
        raise ValueError("smoothing must be > 0")
    if len(states) < 2:
        return IrreversibilityDiagnostics(0.0, 0.0, 0.0, 0, 0, smoothing, 0.0, False)

    forward = Counter(zip(states[:-1], states[1:]))
    reverse = Counter({(b, a): c for (a, b), c in forward.items()})
    keys = sorted(set(forward) | set(reverse), key=repr)
    distinct_states = len(set(states))

    pf = _dirichlet(forward, keys, smoothing)
    pr = _dirichlet(reverse, keys, smoothing)
    mid = {k: 0.5 * (pf[k] + pr[k]) for k in keys}

    js = 0.5 * _kl_bits(pf, mid) + 0.5 * _kl_bits(pr, mid)
    kl = _kl_bits(pf, pr)
    entropy = -sum(p * math.log2(p) for p in pf.values() if p > 0)

    transitions = sum(forward.values())
    per_key = transitions / len(keys) if keys else 0.0

    return IrreversibilityDiagnostics(
        forward_reverse_js=max(0.0, min(1.0, js)),
        forward_reverse_kl=kl,
        transition_entropy_bits=entropy,
        unique_transitions=len(keys),
        distinct_states=distinct_states,
        smoothing=smoothing,
        transitions_per_key=per_key,
        identifiable=(distinct_states >= MIN_DISTINCT_STATES
                      and per_key >= MIN_TRANSITIONS_PER_KEY),
        calibrated=False,
        predictive=False,
    )
