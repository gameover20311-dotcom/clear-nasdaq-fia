"""Explicit V2 incremental-information screen against existing FIA.

The architectural question for UMSE V2 is not whether its features are complex;
it is whether they add information about future outcomes conditional on what FIA
already knows: I(UMSE_t ; Y_future | FIA_t) > 0.

This module deliberately reuses the repaired V1 conditional-permutation null.
A significant result is screening evidence only. It is never calibration,
promotion evidence, or proof of edge.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Sequence

from umse_master.significance import (
    EvidenceStatus as NullStatus,
    NullCalibratedEstimate,
    incremental_information_evidence,
)

from .contracts import EvidenceStatus


@dataclass(frozen=True)
class V2IncrementalInformation:
    status: EvidenceStatus
    estimate: NullCalibratedEstimate
    significant_screen: bool
    promotion_eligible: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.promotion_eligible:
            raise ValueError("incremental-information screening cannot authorize promotion")


def evaluate_incremental_information(
    umse_series: Sequence[Hashable],
    future_series: Sequence[Hashable],
    fia_series: Sequence[Hashable],
    *,
    permutations: int = 999,
    alpha: float = 0.01,
    seed: int = 20260912,
) -> V2IncrementalInformation:
    """Evaluate I(UMSE; Y_future | FIA) against a conditional permutation null."""

    estimate = incremental_information_evidence(
        umse_series,
        future_series,
        fia_series,
        permutations=permutations,
        alpha=alpha,
        seed=seed,
    )

    if estimate.status == NullStatus.INSUFFICIENT_SAMPLE:
        status = EvidenceStatus.INSUFFICIENT_DATA
    elif estimate.status == NullStatus.NOT_IDENTIFIABLE_WITH_CURRENT_DATA:
        status = EvidenceStatus.NOT_IDENTIFIABLE
    else:
        status = EvidenceStatus.UNCALIBRATED

    reasons = [
        "CONDITIONAL_INFORMATION_SCREEN_ONLY",
        "RAW_POSITIVE_CMI_IS_NOT_EVIDENCE",
        "NOT_PROMOTION_EVIDENCE",
    ]
    if estimate.significant:
        reasons.append("INCREMENTAL_INFORMATION_SCREEN_SIGNIFICANT_UNCALIBRATED")
    else:
        reasons.append("INCREMENTAL_INFORMATION_NOT_ESTABLISHED")

    return V2IncrementalInformation(
        status=status,
        estimate=estimate,
        significant_screen=estimate.significant,
        promotion_eligible=False,
        reasons=tuple(reasons),
    )
