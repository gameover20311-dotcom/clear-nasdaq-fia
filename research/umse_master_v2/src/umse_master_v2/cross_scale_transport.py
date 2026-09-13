from __future__ import annotations

from dataclasses import dataclass
import math

from .contracts import EvidenceStatus


@dataclass(frozen=True)
class TransportConfig:
    target_horizon_seconds: float
    minimum_survival_weight: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.target_horizon_seconds) or self.target_horizon_seconds <= 0:
            raise ValueError("target_horizon_seconds must be finite and > 0")
        if not 0 < self.minimum_survival_weight <= 1:
            raise ValueError("minimum_survival_weight must be in (0,1]")


@dataclass(frozen=True)
class CrossScaleTransport:
    status: EvidenceStatus
    source_half_life_seconds: float | None
    target_horizon_seconds: float
    survival_weight: float | None
    transport_eligible: bool
    calibrated: bool
    reasons: tuple[str, ...]


def assess_transport(
    *,
    source_status: EvidenceStatus,
    measured_half_life_seconds: float | None,
    config: TransportConfig,
) -> CrossScaleTransport:
    """Gate microstructure evidence before it can survive to longer horizons.

    The survival law is the definition of half-life: w = 2^(-horizon/half_life).
    This does not assert that a market feature truly follows exponential decay;
    the half-life must already have been measured by an eligible upstream module.
    The minimum survival threshold is caller-supplied protocol, not a fitted
    constant hidden in this function.
    """

    if source_status in {
        EvidenceStatus.PROTOCOL_INELIGIBLE,
        EvidenceStatus.INSUFFICIENT_DATA,
        EvidenceStatus.NOT_IDENTIFIABLE,
        EvidenceStatus.DEGRADED,
    }:
        return CrossScaleTransport(
            status=source_status,
            source_half_life_seconds=measured_half_life_seconds,
            target_horizon_seconds=config.target_horizon_seconds,
            survival_weight=None,
            transport_eligible=False,
            calibrated=False,
            reasons=("SOURCE_EVIDENCE_NOT_ELIGIBLE_FOR_TRANSPORT",),
        )

    if measured_half_life_seconds is None:
        return CrossScaleTransport(
            status=EvidenceStatus.NOT_IDENTIFIABLE,
            source_half_life_seconds=None,
            target_horizon_seconds=config.target_horizon_seconds,
            survival_weight=None,
            transport_eligible=False,
            calibrated=False,
            reasons=("MEASURED_HALF_LIFE_REQUIRED",),
        )
    half_life = float(measured_half_life_seconds)
    if not math.isfinite(half_life) or half_life <= 0:
        raise ValueError("measured_half_life_seconds must be finite and > 0")

    weight = math.exp(-math.log(2.0) * config.target_horizon_seconds / half_life)
    eligible = weight >= config.minimum_survival_weight
    return CrossScaleTransport(
        status=EvidenceStatus.UNCALIBRATED,
        source_half_life_seconds=half_life,
        target_horizon_seconds=config.target_horizon_seconds,
        survival_weight=weight,
        transport_eligible=eligible,
        calibrated=False,
        reasons=(
            "MEASURED_PERSISTENCE_GATE_ONLY",
            "TRANSPORT_ELIGIBILITY_IS_NOT_PREDICTIVE_EDGE",
        ),
    )
