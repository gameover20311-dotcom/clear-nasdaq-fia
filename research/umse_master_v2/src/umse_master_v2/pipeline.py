from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Iterable, Sequence

from umse_master.liquidity import OrderBookSnapshot

from .contracts import EvidenceStatus, MBORecord
from .cross_scale_transport import CrossScaleTransport, TransportConfig, assess_transport
from .information_velocity import InformationVelocityReport, TimedShock, estimate_information_velocity
from .leadlag_null import LeadLagEvidence, circular_shift_leadlag_evidence
from .orderbook_memory import OrderBookMemory, estimate_orderbook_memory
from .queue_hazard import QueueLifetimeDiagnostics, kaplan_meier_queue_lifetime
from .queue_survival import QueueSurvivalReport, reconstruct_queue_survival
from .resistance_field import ResistanceConfig, ResistanceField, estimate_resistance_field


@dataclass(frozen=True)
class V2PipelineConfig:
    sequence_domain_complete: bool
    resistance: ResistanceConfig
    source_node: str
    target_node: str
    max_lead_lag_seconds: float
    info_minimum_pairs: int = 5
    leadlag_minimum_events_per_node: int = 20
    leadlag_permutations: int = 999
    leadlag_alpha: float = 0.01
    leadlag_seed: int = 20260912
    order_memory_max_lag_steps: int = 12
    order_memory_max_interval_cv: float = 0.50
    queue_hazard_minimum_orders: int = 10
    transport_target_horizon_seconds: float = 4 * 3600.0
    transport_minimum_survival_weight: float = 0.01
    max_age_seconds: float | None = None


@dataclass(frozen=True)
class V2ShadowDiagnostics:
    queue_survival: QueueSurvivalReport
    queue_lifetime: QueueLifetimeDiagnostics | None
    orderbook_memory: OrderBookMemory
    resistance_field: ResistanceField
    information_velocity: InformationVelocityReport
    leadlag_evidence: LeadLagEvidence
    cross_scale_transport: CrossScaleTransport
    evidence_hash: str
    predictive_mapping_frozen: bool = False
    predictive_edge_proven: bool = False
    production_effect: bool = False

    def __post_init__(self) -> None:
        if self.predictive_mapping_frozen or self.predictive_edge_proven or self.production_effect:
            raise ValueError("V2 shadow diagnostics cannot claim production/predictive status")


def _hash_payload(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def run_v2_shadow(
    *,
    decision_time_utc: datetime,
    mbo_records: Iterable[MBORecord],
    book_snapshots: Sequence[OrderBookSnapshot],
    shocks: Iterable[TimedShock],
    config: V2PipelineConfig,
) -> V2ShadowDiagnostics:
    """Run every implemented V2 live research component in one fail-closed path.

    This is deliberately a research/shadow orchestrator. It does not generate a
    4H/8H trading probability or mutate BASE_FIA. Model competition remains a
    separate validation-time operation because it requires realized outcomes.
    """

    mbo = tuple(mbo_records)
    shock_rows = tuple(shocks)
    books = tuple(book_snapshots)

    queue = reconstruct_queue_survival(
        mbo,
        decision_time_utc,
        max_age_seconds=config.max_age_seconds,
        sequence_domain_complete=config.sequence_domain_complete,
    )
    queue_lifetime = None
    if queue.status == EvidenceStatus.OBSERVED:
        queue_lifetime = kaplan_meier_queue_lifetime(
            queue.observations,
            minimum_orders=config.queue_hazard_minimum_orders,
        )

    memory = estimate_orderbook_memory(
        books,
        decision_time_utc,
        max_lag_steps=config.order_memory_max_lag_steps,
        max_interval_cv=config.order_memory_max_interval_cv,
    )

    if books:
        causal_books = [b for b in books if b.eligible_at(decision_time_utc)]
    else:
        causal_books = []
    if causal_books:
        latest = max(causal_books, key=lambda b: (b.event_time_utc, b.provenance_id))
        resistance = estimate_resistance_field(
            latest,
            mbo,
            decision_time_utc,
            config.resistance,
            max_age_seconds=config.max_age_seconds,
        )
    else:
        resistance = ResistanceField(
            status=EvidenceStatus.INSUFFICIENT_DATA,
            bid_resistance=None,
            ask_resistance=None,
            directional_asymmetry=None,
            bid_depth_share=None,
            ask_depth_share=None,
            bid_provision_share=None,
            ask_provision_share=None,
            bid_depletion_share=None,
            ask_depletion_share=None,
            calibrated=False,
            reasons=("NO_CAUSAL_BOOK_SNAPSHOT",),
        )

    velocity = estimate_information_velocity(
        shock_rows,
        decision_time_utc,
        source_node=config.source_node,
        target_node=config.target_node,
        max_lag_seconds=config.max_lead_lag_seconds,
        minimum_pairs=config.info_minimum_pairs,
    )

    leadlag = circular_shift_leadlag_evidence(
        shock_rows,
        decision_time_utc,
        source_node=config.source_node,
        target_node=config.target_node,
        max_lag_seconds=config.max_lead_lag_seconds,
        permutations=config.leadlag_permutations,
        alpha=config.leadlag_alpha,
        seed=config.leadlag_seed,
        minimum_events_per_node=config.leadlag_minimum_events_per_node,
    )

    transport = assess_transport(
        source_status=memory.status,
        measured_half_life_seconds=memory.approximate_half_life_seconds,
        config=TransportConfig(
            target_horizon_seconds=config.transport_target_horizon_seconds,
            minimum_survival_weight=config.transport_minimum_survival_weight,
        ),
    )

    payload = {
        "decision_time_utc": decision_time_utc.isoformat(),
        "mbo_provenance": sorted(r.provenance_id for r in mbo if r.eligible_at(decision_time_utc, max_age_seconds=config.max_age_seconds)),
        "book_provenance": sorted(b.provenance_id for b in causal_books),
        "shock_provenance": sorted(s.provenance_id for s in shock_rows if s.eligible_at(decision_time_utc)),
        "queue_status": queue.status.value,
        "memory_status": memory.status.value,
        "resistance_status": resistance.status.value,
        "velocity_status": velocity.status.value,
        "leadlag_status": leadlag.status.value,
        "transport_status": transport.status.value,
        "config": {
            "sequence_domain_complete": config.sequence_domain_complete,
            "source_node": config.source_node,
            "target_node": config.target_node,
            "max_lead_lag_seconds": config.max_lead_lag_seconds,
            "transport_target_horizon_seconds": config.transport_target_horizon_seconds,
            "transport_minimum_survival_weight": config.transport_minimum_survival_weight,
            "max_age_seconds": config.max_age_seconds,
            "resistance": {
                "depth_weight": config.resistance.depth_weight,
                "provision_weight": config.resistance.provision_weight,
                "depletion_weight": config.resistance.depletion_weight,
                "levels": config.resistance.levels,
            },
        },
    }

    return V2ShadowDiagnostics(
        queue_survival=queue,
        queue_lifetime=queue_lifetime,
        orderbook_memory=memory,
        resistance_field=resistance,
        information_velocity=velocity,
        leadlag_evidence=leadlag,
        cross_scale_transport=transport,
        evidence_hash=_hash_payload(payload),
        predictive_mapping_frozen=False,
        predictive_edge_proven=False,
        production_effect=False,
    )
