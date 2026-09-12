from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Mapping, Sequence


DIRECTIONS = ("bullish", "bearish", "neutral")


def _validated_probs(p: Mapping[str, float]) -> Dict[str, float]:
    out = {k: float(p.get(k, 0.0)) for k in DIRECTIONS}
    if any((not math.isfinite(v) or v < 0) for v in out.values()):
        raise ValueError("probabilities must be finite and >= 0")
    total = sum(out.values())
    if total <= 0:
        raise ValueError("probabilities require positive mass")
    return {k: v / total for k, v in out.items()}


@dataclass(frozen=True)
class ExpertOpinion:
    name: str
    probabilities: Mapping[str, float]
    reliability: float
    data_quality: float
    redundancy_group: str
    calibrated: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.redundancy_group.strip():
            raise ValueError("name and redundancy_group must be non-empty")
        _validated_probs(self.probabilities)
        if not 0 <= self.reliability <= 1 or not 0 <= self.data_quality <= 1:
            raise ValueError("reliability and data_quality must be in [0,1]")


@dataclass(frozen=True)
class FusionResult:
    probabilities: Mapping[str, float]
    entropy: float
    effective_expert_weight: float
    calibrated: bool
    predictive: bool = False


def reliability_weighted_fusion(experts: Sequence[ExpertOpinion]) -> FusionResult:
    if not experts:
        return FusionResult({k: 1 / 3 for k in DIRECTIONS}, 1.0, 0.0, False, False)
    group_counts: Dict[str, int] = {}
    for e in experts:
        group_counts[e.redundancy_group] = group_counts.get(e.redundancy_group, 0) + 1
    log_scores = {k: math.log(1 / 3) for k in DIRECTIONS}
    total_w = 0.0
    all_calibrated = True
    for e in experts:
        probs = _validated_probs(e.probabilities)
        redundancy_discount = 1.0 / group_counts[e.redundancy_group]
        w = e.reliability * e.data_quality * redundancy_discount
        total_w += w
        all_calibrated = all_calibrated and e.calibrated
        for k in DIRECTIONS:
            log_scores[k] += w * math.log(max(1e-12, probs[k]))
    m = max(log_scores.values())
    exp_scores = {k: math.exp(v - m) for k, v in log_scores.items()}
    z = sum(exp_scores.values())
    probs = {k: v / z for k, v in exp_scores.items()}
    h = -sum(p * math.log(max(1e-12, p)) for p in probs.values()) / math.log(3)
    return FusionResult(probs, max(0.0, min(1.0, h)), total_w, all_calibrated, False)
