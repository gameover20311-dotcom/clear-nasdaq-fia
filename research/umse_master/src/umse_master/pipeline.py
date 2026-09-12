from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from typing import Iterable, Mapping, Optional, Sequence, Tuple

from .contracts import CausalObservation, ShadowSnapshot
from .criticality import CriticalityDiagnostics, compute_criticality
from .cross_scale import CrossScaleReport, ScaleEvidence, assess_cross_scale
from .events import EventWindow, MarketEvent
from .hawkes import HawkesDiagnostics, HawkesNetworkConfig, hawkes_diagnostics
from .impact import ImpactContext, ResponseSurprise, compute_response_surprise
from .liquidity import LiquidityField, OrderBookSnapshot, estimate_liquidity_field
from .mechanisms import MechanismCompetition, MechanismEvidence, compete_mechanisms
from .mst import MSTComponents, MSTResult, compute_mst
from .primitives import PrimitiveFeatures, compute_primitives
from .shadow_engine import assess_input_quality, build_fail_closed_snapshot
from .state import StateEvidence, StateInference, infer_state


@dataclass(frozen=True)
class UMSEResearchDiagnostics:
    primitives: PrimitiveFeatures
    liquidity: Optional[LiquidityField]
    response_surprise: Optional[ResponseSurprise]
    hawkes: Optional[HawkesDiagnostics]
    criticality: Optional[CriticalityDiagnostics]
    mechanisms: MechanismCompetition
    state: StateInference
    cross_scale: CrossScaleReport
    mst: MSTResult
    evidence_hash: str
    predictive_mapping_frozen: bool = False
    production_effect: bool = False


@dataclass(frozen=True)
class UMSEShadowRun:
    snapshot: ShadowSnapshot
    diagnostics: UMSEResearchDiagnostics


def _hash_payload(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


# Sweep count at which flow urgency is treated as saturated. UNCALIBRATED
# protocol constant, named here rather than buried as a literal.
SWEEP_URGENCY_SCALE = 5.0


def run_umse_shadow(
    *,
    observations: Iterable[CausalObservation],
    events: Iterable[MarketEvent],
    decision_time_utc: datetime,
    book: Optional[OrderBookSnapshot] = None,
    hawkes_config: Optional[HawkesNetworkConfig] = None,
    realized_volatility: float = 0.0,
    recovery_responses: Sequence[float] = (),
    state_series: Sequence[float] = (),
    scale_evidence: Iterable[ScaleEvidence] = (),
) -> UMSEShadowRun:
    rows = tuple(events)
    window = EventWindow(rows)
    primitives = compute_primitives(window, decision_time_utc)
    liquidity = estimate_liquidity_field(book, decision_time_utc, rows) if book is not None else None
    effective_liquidity = (
        liquidity.weighted_bid_depth + liquidity.weighted_ask_depth if liquidity is not None else 0.0
    )
    response = None
    if primitives.observed_price_change is not None:
        response = compute_response_surprise(
            primitives.observed_price_change,
            ImpactContext(
                primitives.signed_aggressive_volume,
                effective_liquidity,
                max(0.0, float(realized_volatility)),
                liquidity.resilience_proxy if liquidity is not None else 0.0,
            ),
        )
    hawkes = hawkes_diagnostics(hawkes_config, rows, decision_time_utc) if hawkes_config is not None else None

    # CRITICALITY.
    # relative_liquidity_change is None here and that is deliberate. A single
    # book snapshot contains no liquidity CHANGE, so the elasticity component
    # is genuinely unavailable. The pre-repair pipeline passed the book's
    # depth_imbalance into this slot, which is a cross-sectional asymmetry at
    # one instant; a balanced book drove it to zero and the component saturated
    # at maximum criticality. Supplying None marks the component unavailable
    # instead of fabricating it.
    criticality = compute_criticality(
        hawkes_spectral_radius=hawkes.spectral_radius if hawkes is not None else None,
        state_series=state_series,
        recovery_responses=recovery_responses,
        relative_price_change=None,
        relative_liquidity_change=None,
    )
    price_response_signed = 0.0
    if primitives.observed_price_change is not None:
        price_response_signed = max(-1.0, min(1.0, primitives.observed_price_change / (abs(primitives.observed_price_change) + 1.0)))
    mech_evidence = MechanismEvidence(
        aggression_imbalance=max(-1.0, min(1.0, primitives.aggression_imbalance)),
        price_response_signed=price_response_signed,
        replenishment_ratio=max(0.0, min(1.0, primitives.replenishment_ratio)),
        depth_imbalance=liquidity.depth_imbalance if liquidity is not None else 0.0,
        resilience=liquidity.resilience_proxy if liquidity is not None else 0.0,
        failed_response_score=response.failed_response_score if response is not None else 0.0,
        liquidity_thinness=liquidity.thinness if liquidity is not None else 1.0,
        volatility_stress=max(0.0, min(1.0, float(realized_volatility) / (1.0 + float(realized_volatility)))),
    )
    mechanisms = compete_mechanisms(mech_evidence)
    state = infer_state(
        StateEvidence(
            mechanism_weights=mechanisms.hypothesis_weights,
            criticality=criticality.candidate_index if criticality.candidate_index is not None else 0.5,
            resilience=mech_evidence.resilience,
            liquidity_thinness=mech_evidence.liquidity_thinness,
            volatility_stress=mech_evidence.volatility_stress,
            structural_entropy=1.0 - mechanisms.concentration,
        )
    )
    # The 4H/8H gate needs a MEASURED information half-life. None is available
    # from a single decision point, so the gate stays closed.
    cross = assess_cross_scale(scale_evidence, measured_half_life_minutes=None)

    quality = assess_input_quality(observations, decision_time_utc)

    # MST.
    # Every component now names the observable it came from. The pre-repair
    # wiring put state.entropy into structural_stress, entropy AND uncertainty,
    # and repeated abs(aggression_imbalance) inside flow_urgency, so one
    # variable occupied four of nine slots. Components with no independent
    # observable are None, and compute_mst refuses to produce a value rather
    # than filling them. MST is consequently UNAVAILABLE here, which is the
    # honest result: the construct needs nine independent observables and this
    # engine cannot supply nine independent observables.
    sweep_intensity = min(1.0, (primitives.buy_sweeps + primitives.sell_sweeps) / SWEEP_URGENCY_SCALE)
    mst = compute_mst(
        MSTComponents(
            pressure=min(1.0, abs(primitives.aggression_imbalance)),
            criticality=criticality.candidate_index,
            flow_urgency=sweep_intensity,
            information_asymmetry=mechanisms.directional_identification,
            structural_stress=state.entropy,
            entropy=None,          # no observable independent of state dispersion
            redundancy=None,       # UNKNOWN, and never silently zero
            uncertainty=None,      # no observable independent of state dispersion
            data_degradation=max(0.0, min(1.0, 1.0 - quality.quality_score)),
            sources={
                "pressure": "primitives.aggression_imbalance",
                "criticality": "criticality.candidate_index",
                "flow_urgency": "primitives.sweep_counts",
                "information_asymmetry": "mechanisms.directional_identification",
                "structural_stress": "state.entropy",
                "data_degradation": "input_quality.quality_score",
            },
        )
    )
    snapshot = build_fail_closed_snapshot(observations, decision_time_utc)
    payload = {
        "decision_time": decision_time_utc.isoformat(),
        "event_ids": [e.provenance_id for e in window.causal_slice(decision_time_utc)],
        "book_id": book.provenance_id if book is not None else None,
        "state": state.top_state,
        "mst": mst.original_concept_value,
        "mst_status": mst.status.value,
    }
    diagnostics = UMSEResearchDiagnostics(
        primitives=primitives,
        liquidity=liquidity,
        response_surprise=response,
        hawkes=hawkes,
        criticality=criticality,
        mechanisms=mechanisms,
        state=state,
        cross_scale=cross,
        mst=mst,
        evidence_hash=_hash_payload(payload),
        predictive_mapping_frozen=False,
        production_effect=False,
    )
    return UMSEShadowRun(snapshot=snapshot, diagnostics=diagnostics)
