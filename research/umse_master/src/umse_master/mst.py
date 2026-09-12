from __future__ import annotations

from dataclasses import dataclass
import math


def _01(x: float, name: str) -> float:
    y = float(x)
    if not math.isfinite(y) or y < 0 or y > 1:
        raise ValueError(f"{name} must be in [0,1]")
    return y


@dataclass(frozen=True)
class MSTComponents:
    pressure: float
    criticality: float
    flow_urgency: float
    information_asymmetry: float
    structural_stress: float
    entropy: float
    redundancy: float
    uncertainty: float
    data_degradation: float

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _01(getattr(self, name), name)


@dataclass(frozen=True)
class MSTResult:
    original_concept_value: float
    log_stable_value: float
    redundancy_penalty: float
    calibrated: bool = False
    predictive: bool = False


def compute_mst(c: MSTComponents) -> MSTResult:
    numerator = c.pressure * c.criticality * c.flow_urgency * c.information_asymmetry * c.structural_stress
    denominator = 1.0 + c.entropy + c.redundancy + c.uncertainty + c.data_degradation
    original = numerator / denominator
    # Alternative stable formulation for research comparison; still unvalidated.
    positive_log = sum(math.log1p(x) for x in (
        c.pressure, c.criticality, c.flow_urgency, c.information_asymmetry, c.structural_stress
    ))
    negative_log = sum(math.log1p(x) for x in (
        c.entropy, c.redundancy, c.uncertainty, c.data_degradation
    ))
    stable = 1.0 / (1.0 + math.exp(-(positive_log - negative_log)))
    return MSTResult(
        original_concept_value=max(0.0, min(1.0, original)),
        log_stable_value=max(0.0, min(1.0, stable)),
        redundancy_penalty=c.redundancy,
        calibrated=False,
        predictive=False,
    )
