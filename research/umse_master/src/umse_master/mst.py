"""Market State Tension: a SPECULATIVE candidate construct, not a score.

WHAT THE AUDIT PROVED
---------------------
The pipeline fed `state.entropy` into THREE of the nine supposedly independent
MST components -- structural_stress in the numerator, entropy and uncertainty
in the denominator -- so the formula was not the stated combination of distinct
signals. `abs(aggression_imbalance)` appeared in two numerator factors and, the
numerator being a product, was effectively squared. `redundancy`, the very term
meant to penalise double counting, was hardcoded to 0.0 at the only call site.

REPAIR
------
Components are Optional and carry a `sources` map naming the underlying
observable each one came from. compute_mst refuses to produce a value when two
components share a source, or when any component is missing. Unknown redundancy
is None, never 0.0.

The result is that MST is frequently UNAVAILABLE, which is the correct and
honest outcome: the construct requires nine independent observables and the
current engine cannot supply nine independent observables. The hypothesis
registry already rates this construct SPECULATIVE with the kill rule "Reject
MST if it is redundant with its components or sensitive to arbitrary formula
choices". This module now enforces the first half of that rule mechanically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Dict, Mapping, Optional, Tuple

NUMERATOR_COMPONENTS = (
    "pressure", "criticality", "flow_urgency",
    "information_asymmetry", "structural_stress",
)
DENOMINATOR_COMPONENTS = ("entropy", "redundancy", "uncertainty", "data_degradation")
ALL_COMPONENTS = NUMERATOR_COMPONENTS + DENOMINATOR_COMPONENTS


class MSTStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE_MISSING_COMPONENTS = "UNAVAILABLE_MISSING_COMPONENTS"
    UNAVAILABLE_REDUNDANT_SOURCES = "UNAVAILABLE_REDUNDANT_SOURCES"


def _opt01(x: Optional[float], name: str) -> Optional[float]:
    if x is None:
        return None
    y = float(x)
    if not math.isfinite(y) or y < 0 or y > 1:
        raise ValueError(f"{name} must be in [0,1] or None")
    return y


@dataclass(frozen=True)
class MSTComponents:
    pressure: Optional[float]
    criticality: Optional[float]
    flow_urgency: Optional[float]
    information_asymmetry: Optional[float]
    structural_stress: Optional[float]
    entropy: Optional[float]
    redundancy: Optional[float]
    uncertainty: Optional[float]
    data_degradation: Optional[float]
    sources: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ALL_COMPONENTS:
            _opt01(getattr(self, name), name)


@dataclass(frozen=True)
class MSTResult:
    original_concept_value: Optional[float]
    log_stable_value: Optional[float]
    redundancy_penalty: Optional[float]
    status: MSTStatus
    unavailable_components: Tuple[str, ...] = ()
    redundant_source_groups: Tuple[Tuple[str, ...], ...] = ()
    calibrated: bool = False
    predictive: bool = False
    promotion_eligible: bool = False


def compute_mst(c: MSTComponents) -> MSTResult:
    values: Dict[str, Optional[float]] = {n: getattr(c, n) for n in ALL_COMPONENTS}
    missing = tuple(n for n in ALL_COMPONENTS if values[n] is None)

    # Two components drawn from the same observable are not two pieces of
    # evidence. Detect it and refuse rather than silently multiply.
    by_source: Dict[str, list] = {}
    for name in ALL_COMPONENTS:
        src = c.sources.get(name)
        if src is not None and values[name] is not None:
            by_source.setdefault(src, []).append(name)
    redundant = tuple(tuple(v) for v in by_source.values() if len(v) > 1)

    if redundant:
        return MSTResult(None, None, values.get("redundancy"),
                         MSTStatus.UNAVAILABLE_REDUNDANT_SOURCES,
                         missing, redundant)
    if missing:
        return MSTResult(None, None, values.get("redundancy"),
                         MSTStatus.UNAVAILABLE_MISSING_COMPONENTS,
                         missing, redundant)

    numerator = 1.0
    for name in NUMERATOR_COMPONENTS:
        numerator *= float(values[name])
    denominator = 1.0 + sum(float(values[n]) for n in DENOMINATOR_COMPONENTS)
    original = numerator / denominator

    positive_log = sum(math.log1p(float(values[n])) for n in NUMERATOR_COMPONENTS)
    negative_log = sum(math.log1p(float(values[n])) for n in DENOMINATOR_COMPONENTS)
    stable = 1.0 / (1.0 + math.exp(-(positive_log - negative_log)))

    return MSTResult(
        original_concept_value=max(0.0, min(1.0, original)),
        log_stable_value=max(0.0, min(1.0, stable)),
        redundancy_penalty=float(values["redundancy"]),
        status=MSTStatus.AVAILABLE,
        unavailable_components=(),
        redundant_source_groups=(),
        calibrated=False,
        predictive=False,
        promotion_eligible=False,
    )
