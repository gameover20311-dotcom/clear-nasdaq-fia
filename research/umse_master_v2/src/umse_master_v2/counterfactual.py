"""Fail-closed observational counterfactual diagnostics for UMSE V2.

This module does not manufacture causality from observational market data.
It estimates a transparent, stratified treated-vs-control contrast only where
there is empirical overlap.  Missing overlap, sparse strata, or post-treatment
conditioning block the estimate.

Even a clean estimate remains `causal_claim_allowed=False`.  Causal promotion
would require a separately preregistered design with defensible intervention
semantics and assumptions; this module is a falsification/diagnostic surface.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Hashable, Iterable

from .contracts import EvidenceStatus


@dataclass(frozen=True)
class CounterfactualObservation:
    stratum: Hashable
    treated: bool
    outcome: float
    pre_treatment_only: bool
    provenance_id: str

    def __post_init__(self) -> None:
        if not str(self.provenance_id).strip():
            raise ValueError("provenance_id must be non-empty")
        if not math.isfinite(float(self.outcome)):
            raise ValueError("outcome must be finite")


@dataclass(frozen=True)
class StratumEffect:
    stratum: Hashable
    treated_n: int
    control_n: int
    treated_mean: float
    control_mean: float
    difference: float
    weight: float


@dataclass(frozen=True)
class CounterfactualDiagnostic:
    status: EvidenceStatus
    estimate: float | None
    covered_observations: int
    total_observations: int
    overlap_fraction: float
    stratum_effects: tuple[StratumEffect, ...]
    reasons: tuple[str, ...]
    observational_only: bool = True
    causal_claim_allowed: bool = False
    calibrated: bool = False
    predictive: bool = False
    promotion_eligible: bool = False

    def __post_init__(self) -> None:
        if self.causal_claim_allowed or self.calibrated or self.predictive or self.promotion_eligible:
            raise ValueError("observational counterfactual diagnostics cannot prove/promote causality or edge")


def estimate_stratified_counterfactual(
    rows: Iterable[CounterfactualObservation],
    *,
    minimum_per_arm_per_stratum: int = 5,
    minimum_overlap_fraction: float = 0.60,
) -> CounterfactualDiagnostic:
    """Estimate a within-stratum observational contrast with strict overlap.

    Weighting uses the number of observations in each valid stratum.  Any row
    marked as not pre-treatment-only makes the design protocol ineligible,
    because conditioning on post-treatment information can create spurious
    effects.
    """
    if minimum_per_arm_per_stratum < 1:
        raise ValueError("minimum_per_arm_per_stratum must be >= 1")
    if not 0.0 < minimum_overlap_fraction <= 1.0:
        raise ValueError("minimum_overlap_fraction must be in (0,1]")

    data = tuple(rows)
    if not data:
        return CounterfactualDiagnostic(
            status=EvidenceStatus.INSUFFICIENT_DATA,
            estimate=None,
            covered_observations=0,
            total_observations=0,
            overlap_fraction=0.0,
            stratum_effects=(),
            reasons=("NO_OBSERVATIONS",),
        )

    if any(not r.pre_treatment_only for r in data):
        return CounterfactualDiagnostic(
            status=EvidenceStatus.PROTOCOL_INELIGIBLE,
            estimate=None,
            covered_observations=0,
            total_observations=len(data),
            overlap_fraction=0.0,
            stratum_effects=(),
            reasons=("POST_TREATMENT_CONDITIONING_PRESENT",),
        )

    buckets: dict[Hashable, dict[bool, list[float]]] = {}
    for row in data:
        buckets.setdefault(row.stratum, {True: [], False: []})[bool(row.treated)].append(float(row.outcome))

    valid: list[StratumEffect] = []
    covered = 0
    for key, arms in buckets.items():
        treated = arms[True]
        control = arms[False]
        if len(treated) < minimum_per_arm_per_stratum or len(control) < minimum_per_arm_per_stratum:
            continue
        n = len(treated) + len(control)
        tm = sum(treated) / len(treated)
        cm = sum(control) / len(control)
        covered += n
        valid.append(
            StratumEffect(
                stratum=key,
                treated_n=len(treated),
                control_n=len(control),
                treated_mean=tm,
                control_mean=cm,
                difference=tm - cm,
                weight=float(n),
            )
        )

    overlap = covered / len(data)
    if not valid:
        return CounterfactualDiagnostic(
            status=EvidenceStatus.NOT_IDENTIFIABLE,
            estimate=None,
            covered_observations=covered,
            total_observations=len(data),
            overlap_fraction=overlap,
            stratum_effects=(),
            reasons=("NO_STRATUM_WITH_BOTH_TREATMENT_ARMS",),
        )

    if overlap < minimum_overlap_fraction:
        return CounterfactualDiagnostic(
            status=EvidenceStatus.NOT_IDENTIFIABLE,
            estimate=None,
            covered_observations=covered,
            total_observations=len(data),
            overlap_fraction=overlap,
            stratum_effects=tuple(valid),
            reasons=("INSUFFICIENT_EMPIRICAL_OVERLAP",),
        )

    total_weight = sum(x.weight for x in valid)
    estimate = sum(x.difference * x.weight for x in valid) / total_weight
    return CounterfactualDiagnostic(
        status=EvidenceStatus.UNCALIBRATED,
        estimate=estimate,
        covered_observations=covered,
        total_observations=len(data),
        overlap_fraction=overlap,
        stratum_effects=tuple(valid),
        reasons=(
            "OBSERVATIONAL_STRATIFIED_CONTRAST_ONLY",
            "UNMEASURED_CONFOUNDING_NOT_IDENTIFIED",
            "NO_CAUSAL_CLAIM_WITHOUT_PREREGISTERED_INTERVENTION_SEMANTICS",
        ),
        observational_only=True,
        causal_claim_allowed=False,
        calibrated=False,
        predictive=False,
        promotion_eligible=False,
    )
