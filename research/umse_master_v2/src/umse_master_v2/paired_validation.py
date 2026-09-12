"""V2-specific paired validation architecture.

The primary confirmatory horizon is fixed at 8H.  The 4H horizon is separate
and hierarchical: its scientific interpretation is opened only after the 8H
primary gate succeeds.  Both horizons require prospective locked records and a
preregistered plan whose MODEL/PROTOCOL identities match every record.

This module delegates the numerical Brier/bootstrap gate to the repaired V1
validation implementation, while adding V2 record identity, timing and
hierarchical-horizon contracts around it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Mapping, Sequence

from umse_master.replay import ReplayClass
from umse_master.validation import ConfirmatoryPlan, PairedValidationResult, evaluate_paired_candidate


class Horizon(str, Enum):
    H4 = "4H"
    H8 = "8H"

    @property
    def seconds(self) -> int:
        return 4 * 3600 if self is Horizon.H4 else 8 * 3600


PRIMARY_HORIZON = Horizon.H8


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _nonempty(name: str, value: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} must be non-empty")
    return text


@dataclass(frozen=True)
class V2ValidationPlan:
    plan_id: str
    horizon: Horizon
    preregistered_n: int
    target_delta: float
    registered_at_utc: datetime
    expected_model_fingerprint: str
    expected_protocol_fingerprint: str
    block_size: int = 5
    alpha: float = 0.05
    power_design_reference: str = "REQUIRES_ZERO_ALPHA_FORWARD_PILOT"
    evidence_class: ReplayClass = ReplayClass.FORWARD_OOS

    def __post_init__(self) -> None:
        _nonempty("plan_id", self.plan_id)
        _nonempty("expected_model_fingerprint", self.expected_model_fingerprint)
        _nonempty("expected_protocol_fingerprint", self.expected_protocol_fingerprint)
        _nonempty("power_design_reference", self.power_design_reference)
        object.__setattr__(self, "registered_at_utc", _utc(self.registered_at_utc))
        if int(self.preregistered_n) <= 0:
            raise ValueError("preregistered_n must be > 0")
        if float(self.target_delta) <= 0:
            raise ValueError("target_delta must be > 0")
        if int(self.block_size) <= 0:
            raise ValueError("block_size must be > 0")
        if self.evidence_class is not ReplayClass.FORWARD_OOS:
            raise ValueError("V2 confirmatory plans must be FORWARD_OOS")

    @property
    def is_primary(self) -> bool:
        return self.horizon is PRIMARY_HORIZON


@dataclass(frozen=True)
class V2PairedForecastRecord:
    forecast_id: str
    horizon: Horizon
    locked_at_utc: datetime
    outcome_time_utc: datetime
    base_probabilities: Mapping[str, float]
    candidate_probabilities: Mapping[str, float]
    outcome: str
    evidence_hash: str
    model_fingerprint: str
    protocol_fingerprint: str
    replay_class: ReplayClass = ReplayClass.FORWARD_OOS

    def __post_init__(self) -> None:
        for name in (
            "forecast_id",
            "evidence_hash",
            "model_fingerprint",
            "protocol_fingerprint",
        ):
            _nonempty(name, getattr(self, name))
        object.__setattr__(self, "locked_at_utc", _utc(self.locked_at_utc))
        object.__setattr__(self, "outcome_time_utc", _utc(self.outcome_time_utc))
        if self.outcome not in {"bullish", "bearish", "neutral"}:
            raise ValueError("outcome must be bullish/bearish/neutral")


@dataclass(frozen=True)
class V2HorizonValidation:
    horizon: Horizon
    n: int
    protocol_eligible: bool
    numerical_result: PairedValidationResult | None
    blocking_reasons: tuple[str, ...]

    @property
    def promotion_gate_pass(self) -> bool:
        return bool(
            self.protocol_eligible
            and self.numerical_result is not None
            and self.numerical_result.promotion_gate_pass
        )


@dataclass(frozen=True)
class V2ValidationSuite:
    primary_8h: V2HorizonValidation
    secondary_4h: V2HorizonValidation
    secondary_4h_interpretation_open: bool
    promotion_gate_pass: bool
    blocking_reasons: tuple[str, ...]
    predictive_edge_proven: bool = False

    def __post_init__(self) -> None:
        # Passing a statistical gate is not the same thing as globally proving
        # predictive edge. Promotion is a governed decision after the complete
        # preregistered campaign/audit, not a boolean this object may assert.
        if self.predictive_edge_proven:
            raise ValueError("validation suite cannot self-declare predictive edge proven")


def _protocol_reasons(records: Sequence[V2PairedForecastRecord], plan: V2ValidationPlan) -> list[str]:
    reasons: list[str] = []
    if not records:
        return ["NO_RECORDS"]

    ids = [r.forecast_id for r in records]
    if len(ids) != len(set(ids)):
        reasons.append("DUPLICATE_FORECAST_ID")

    if len(records) != plan.preregistered_n:
        reasons.append("N_DOES_NOT_MATCH_PREREGISTERED_N")

    earliest_lock = min(r.locked_at_utc for r in records)
    if plan.registered_at_utc >= earliest_lock:
        reasons.append("PLAN_NOT_REGISTERED_BEFORE_FIRST_FORECAST")

    for r in records:
        if r.horizon is not plan.horizon:
            reasons.append("MIXED_OR_WRONG_HORIZON")
            break
    for r in records:
        if r.replay_class is not ReplayClass.FORWARD_OOS:
            reasons.append("NON_FORWARD_OOS_RECORD_PRESENT")
            break
    for r in records:
        if r.model_fingerprint != plan.expected_model_fingerprint:
            reasons.append("MODEL_FINGERPRINT_MISMATCH")
            break
    for r in records:
        if r.protocol_fingerprint != plan.expected_protocol_fingerprint:
            reasons.append("PROTOCOL_FINGERPRINT_MISMATCH")
            break
    for r in records:
        minimum_outcome = r.locked_at_utc + timedelta(seconds=plan.horizon.seconds)
        if r.outcome_time_utc < minimum_outcome:
            reasons.append("OUTCOME_RESOLVED_BEFORE_HORIZON")
            break

    return list(dict.fromkeys(reasons))


def evaluate_v2_horizon(
    records: Sequence[V2PairedForecastRecord],
    plan: V2ValidationPlan,
    *,
    seed: int = 56,
) -> V2HorizonValidation:
    rows = tuple(sorted(records, key=lambda r: (r.locked_at_utc, r.forecast_id)))
    reasons = _protocol_reasons(rows, plan)
    if reasons:
        return V2HorizonValidation(
            horizon=plan.horizon,
            n=len(rows),
            protocol_eligible=False,
            numerical_result=None,
            blocking_reasons=tuple(reasons),
        )

    v1_plan = ConfirmatoryPlan(
        plan_id=plan.plan_id,
        preregistered_n=plan.preregistered_n,
        target_delta=plan.target_delta,
        registered_at_utc=plan.registered_at_utc,
        evidence_class=ReplayClass.FORWARD_OOS,
        alpha=plan.alpha,
        block_size=plan.block_size,
        power_design_reference=plan.power_design_reference,
    )
    numerical = evaluate_paired_candidate(
        [r.base_probabilities for r in rows],
        [r.candidate_probabilities for r in rows],
        [r.outcome for r in rows],
        plan=v1_plan,
        seed=seed,
    )
    combined_reasons = tuple(numerical.blocking_reasons)
    return V2HorizonValidation(
        horizon=plan.horizon,
        n=len(rows),
        protocol_eligible=True,
        numerical_result=numerical,
        blocking_reasons=combined_reasons,
    )


def evaluate_v2_suite(
    *,
    records_8h: Sequence[V2PairedForecastRecord],
    plan_8h: V2ValidationPlan,
    records_4h: Sequence[V2PairedForecastRecord],
    plan_4h: V2ValidationPlan,
    seed: int = 56,
) -> V2ValidationSuite:
    if plan_8h.horizon is not Horizon.H8:
        raise ValueError("primary plan must be 8H")
    if plan_4h.horizon is not Horizon.H4:
        raise ValueError("secondary plan must be 4H")

    primary = evaluate_v2_horizon(records_8h, plan_8h, seed=seed)
    secondary = evaluate_v2_horizon(records_4h, plan_4h, seed=seed + 1)

    secondary_open = primary.promotion_gate_pass
    reasons: list[str] = []
    if not primary.promotion_gate_pass:
        reasons.append("PRIMARY_8H_GATE_NOT_PASSED")
    if not secondary.protocol_eligible:
        reasons.append("SECONDARY_4H_PROTOCOL_NOT_ELIGIBLE")

    # Hierarchical gatekeeping: 8H is the sole primary statistical endpoint.
    # 4H must exist as a protocol-valid companion horizon, but its effect does
    # not become a second co-primary hurdle and does not spend alpha unless the
    # primary gate has opened its interpretation.
    promotion = primary.promotion_gate_pass and secondary.protocol_eligible

    return V2ValidationSuite(
        primary_8h=primary,
        secondary_4h=secondary,
        secondary_4h_interpretation_open=secondary_open,
        promotion_gate_pass=promotion,
        blocking_reasons=tuple(reasons),
        predictive_edge_proven=False,
    )
