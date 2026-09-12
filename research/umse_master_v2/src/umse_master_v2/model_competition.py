from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

from .contracts import EvidenceStatus


CLASSES = ("bullish", "bearish", "neutral")


def _normalized(row: Mapping[str, float]) -> dict[str, float]:
    values = {k: float(row.get(k, 0.0)) for k in CLASSES}
    if any(not math.isfinite(v) or v < 0 for v in values.values()):
        raise ValueError("probabilities must be finite and >= 0")
    total = sum(values.values())
    if total <= 0:
        raise ValueError("probabilities require positive mass")
    return {k: v / total for k, v in values.items()}


def multiclass_log_loss(probabilities: Mapping[str, float], outcome: str, epsilon: float = 1e-12) -> float:
    if outcome not in CLASSES:
        raise ValueError(f"outcome must be one of {CLASSES}")
    if epsilon <= 0 or epsilon >= 1:
        raise ValueError("epsilon must be in (0,1)")
    p = _normalized(probabilities)
    return -math.log(max(epsilon, p[outcome]))


@dataclass(frozen=True)
class ComplexityCompetition:
    status: EvidenceStatus
    n: int
    simple_parameters: int
    complex_parameters: int
    simple_mean_log_loss: float | None
    complex_mean_log_loss: float | None
    simple_bic_like: float | None
    complex_bic_like: float | None
    delta_description_length: float | None
    complex_preferred: bool
    predictive_proof: bool
    reasons: tuple[str, ...]


def compare_predictive_complexity(
    simple_probabilities: Sequence[Mapping[str, float]],
    complex_probabilities: Sequence[Mapping[str, float]],
    outcomes: Sequence[str],
    *,
    simple_parameters: int,
    complex_parameters: int,
    minimum_n: int = 30,
) -> ComplexityCompetition:
    """BIC/MDL-style diagnostic for nested or competing probabilistic models.

    The statistic penalizes extra free parameters and asks whether their lower
    log loss is large enough to pay for the complexity. It is a diagnostic only:
    using training/in-sample rows would make it especially optimistic, so this
    function never marks predictive proof or promotion eligibility.
    """

    n = len(outcomes)
    if not (len(simple_probabilities) == len(complex_probabilities) == n):
        raise ValueError("probability and outcome lengths must match")
    if simple_parameters < 0 or complex_parameters < 0:
        raise ValueError("parameter counts must be >= 0")
    if complex_parameters < simple_parameters:
        raise ValueError("complex model parameter count must be >= simple model count")
    if minimum_n < 2:
        raise ValueError("minimum_n must be >= 2")

    if n < minimum_n:
        return ComplexityCompetition(
            status=EvidenceStatus.INSUFFICIENT_DATA,
            n=n,
            simple_parameters=simple_parameters,
            complex_parameters=complex_parameters,
            simple_mean_log_loss=None,
            complex_mean_log_loss=None,
            simple_bic_like=None,
            complex_bic_like=None,
            delta_description_length=None,
            complex_preferred=False,
            predictive_proof=False,
            reasons=("MINIMUM_SAMPLE_NOT_MET",),
        )

    simple_losses = [multiclass_log_loss(p, y) for p, y in zip(simple_probabilities, outcomes)]
    complex_losses = [multiclass_log_loss(p, y) for p, y in zip(complex_probabilities, outcomes)]
    simple_nll = sum(simple_losses)
    complex_nll = sum(complex_losses)

    # -2 log L + k log n, expressed using summed predictive log loss as NLL.
    simple_score = 2.0 * simple_nll + simple_parameters * math.log(n)
    complex_score = 2.0 * complex_nll + complex_parameters * math.log(n)
    delta = simple_score - complex_score  # positive favors complex

    return ComplexityCompetition(
        status=EvidenceStatus.UNCALIBRATED,
        n=n,
        simple_parameters=simple_parameters,
        complex_parameters=complex_parameters,
        simple_mean_log_loss=simple_nll / n,
        complex_mean_log_loss=complex_nll / n,
        simple_bic_like=simple_score,
        complex_bic_like=complex_score,
        delta_description_length=delta,
        complex_preferred=delta > 0,
        predictive_proof=False,
        reasons=(
            "COMPLEXITY_DIAGNOSTIC_ONLY",
            "USE_ONLY_ON_PREDECLARED_EVALUATION_DATA",
            "DO_NOT_TREAT_AS_FORWARD_OOS_PROOF",
        ),
    )
