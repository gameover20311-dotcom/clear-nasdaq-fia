from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Tuple

from .contracts import (
    CausalObservation,
    DataClass,
    HorizonEstimate,
    LatentStateVector,
    QualityState,
    ShadowSnapshot,
    ShadowStatus,
)


@dataclass(frozen=True)
class InputQualityReport:
    total: int
    eligible: int
    validation_grade: int
    proxies: int
    synthetic: int
    stale_or_missing: int
    future_unavailable: int
    quality_score: float
    evidence_ids: Tuple[str, ...]
    data_classes_present: Tuple[str, ...]


def assess_input_quality(
    observations: Iterable[CausalObservation],
    decision_time_utc: datetime,
) -> InputQualityReport:
    if decision_time_utc.tzinfo is None:
        raise ValueError("decision_time_utc must be timezone-aware")
    decision = decision_time_utc.astimezone(timezone.utc)
    rows = tuple(observations)

    eligible = []
    validation_grade = []
    proxies = 0
    synthetic = 0
    stale_or_missing = 0
    future_unavailable = 0

    for obs in rows:
        if obs.is_proxy or obs.data_class == DataClass.PROXY_RESEARCH:
            proxies += 1
        if obs.data_class == DataClass.SYNTHETIC_TEST:
            synthetic += 1
        if obs.quality_state in {
            QualityState.STALE,
            QualityState.MISSING,
            QualityState.INELIGIBLE,
        }:
            stale_or_missing += 1
        if obs.available_time_utc > decision:
            future_unavailable += 1
        if obs.eligible_at(decision):
            eligible.append(obs)
            if obs.can_support_predictive_validation:
                validation_grade.append(obs)

    denominator = max(1, len(rows))
    # Quality score measures availability/quality only. It is not predictive confidence.
    quality_score = len(validation_grade) / denominator

    return InputQualityReport(
        total=len(rows),
        eligible=len(eligible),
        validation_grade=len(validation_grade),
        proxies=proxies,
        synthetic=synthetic,
        stale_or_missing=stale_or_missing,
        future_unavailable=future_unavailable,
        quality_score=quality_score,
        evidence_ids=tuple(sorted({o.provenance_id for o in eligible})),
        data_classes_present=tuple(sorted({o.data_class.value for o in eligible})),
    )


def _neutral_estimate(horizon_hours: int, quality_score: float, reason: str) -> HorizonEstimate:
    # Deliberately non-predictive Phase-0 placeholder. It must not imply edge.
    return HorizonEstimate(
        horizon_hours=horizon_hours,
        state_probabilities={"CHAOS_UNCERTAIN": 1.0},
        mechanism_probabilities={"BALANCED_NOISE": 1.0},
        bullish_probability=1.0 / 3.0,
        bearish_probability=1.0 / 3.0,
        neutral_probability=1.0 / 3.0,
        confidence=0.0,
        propagation_probability=0.0,
        data_quality_score=quality_score,
        reasons=(reason,),
    )


def build_fail_closed_snapshot(
    observations: Iterable[CausalObservation],
    decision_time_utc: datetime,
    generated_at_utc: datetime | None = None,
) -> ShadowSnapshot:
    report = assess_input_quality(observations, decision_time_utc)
    generated = generated_at_utc or datetime.now(timezone.utc)

    if report.total == 0:
        status = ShadowStatus.INSUFFICIENT_DATA
        reason = "NO_INPUT_OBSERVATIONS"
    elif report.future_unavailable > 0 and report.eligible == 0:
        status = ShadowStatus.PROTOCOL_INELIGIBLE
        reason = "NO_CAUSALLY_AVAILABLE_INPUTS"
    elif report.validation_grade == 0:
        status = ShadowStatus.NO_UMSE_EDGE
        reason = "NO_VALIDATION_GRADE_REAL_INPUTS"
    else:
        # Phase 0 has no validated predictive mapping. Even good data must not
        # manufacture a directional estimate before a frozen candidate exists.
        status = ShadowStatus.NO_UMSE_EDGE
        reason = "PHASE_0_NO_VALIDATED_PREDICTIVE_MAPPING"

    latent = LatentStateVector(
        directional_pressure=0.5,
        liquidity_state=0.5,
        aggression_urgency=0.5,
        information_asymmetry=0.5,
        resilience=0.5,
        criticality=0.5,
        structural_regime_entropy=1.0,
        uncertainty=1.0,
    )

    return ShadowSnapshot(
        schema="UMSE_SHADOW_V1",
        generated_at_utc=generated,
        decision_time_utc=decision_time_utc,
        status=status,
        latent_state=latent,
        estimates=(
            _neutral_estimate(4, report.quality_score, reason),
            _neutral_estimate(8, report.quality_score, reason),
        ),
        evidence_ids=report.evidence_ids,
        data_classes_present=report.data_classes_present,
        invalidation_reasons=(reason,),
        production_effect=False,
    )
