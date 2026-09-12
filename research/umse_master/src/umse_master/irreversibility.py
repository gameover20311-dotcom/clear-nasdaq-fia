from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Hashable, Sequence


@dataclass(frozen=True)
class IrreversibilityDiagnostics:
    forward_reverse_kl: float
    transition_entropy_bits: float
    unique_transitions: int
    calibrated: bool = False


def path_irreversibility(states: Sequence[Hashable], epsilon: float = 1e-12) -> IrreversibilityDiagnostics:
    if len(states) < 2:
        return IrreversibilityDiagnostics(0.0, 0.0, 0, False)
    forward = Counter(zip(states[:-1], states[1:]))
    reverse = Counter((b, a) for (a, b), count in forward.items() for _ in range(count))
    keys = set(forward) | set(reverse)
    total_f = sum(forward.values())
    total_r = sum(reverse.values())
    pf = {k: (forward.get(k, 0) + epsilon) for k in keys}
    pr = {k: (reverse.get(k, 0) + epsilon) for k in keys}
    sf, sr = sum(pf.values()), sum(pr.values())
    pf = {k: v / sf for k, v in pf.items()}
    pr = {k: v / sr for k, v in pr.items()}
    kl = sum(pf[k] * math.log(pf[k] / pr[k]) for k in keys)
    entropy = -sum(p * math.log2(p) for p in pf.values())
    return IrreversibilityDiagnostics(kl, entropy, len(keys), False)
