from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Iterable

from umse_master.liquidity import OrderBookSnapshot

from .contracts import EvidenceStatus, MBOAction, MBORecord, Side


@dataclass(frozen=True)
class ResistanceConfig:
    depth_weight: float
    provision_weight: float
    depletion_weight: float
    levels: int = 10

    def __post_init__(self) -> None:
        for name in ("depth_weight", "provision_weight", "depletion_weight"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and >= 0")
        if self.depth_weight + self.provision_weight + self.depletion_weight <= 0:
            raise ValueError("at least one resistance weight must be > 0")
        if self.levels <= 0:
            raise ValueError("levels must be > 0")


@dataclass(frozen=True)
class ResistanceField:
    status: EvidenceStatus
    bid_resistance: float | None
    ask_resistance: float | None
    directional_asymmetry: float | None
    bid_depth_share: float | None
    ask_depth_share: float | None
    bid_provision_share: float | None
    ask_provision_share: float | None
    bid_depletion_share: float | None
    ask_depletion_share: float | None
    calibrated: bool
    reasons: tuple[str, ...]


def _shares(a: float, b: float) -> tuple[float | None, float | None]:
    total = a + b
    if total <= 0:
        return None, None
    return a / total, b / total


def _bounded_resistance(depth_share: float, provision_share: float, depletion_share: float, config: ResistanceConfig) -> float:
    total_w = config.depth_weight + config.provision_weight + config.depletion_weight
    raw = (
        config.depth_weight * depth_share
        + config.provision_weight * provision_share
        - config.depletion_weight * depletion_share
    ) / total_w
    # Maps an uncalibrated signed descriptive score into [0,1] without claiming probability.
    return 0.5 * (math.tanh(2.0 * raw) + 1.0)


def estimate_resistance_field(
    snapshot: OrderBookSnapshot,
    mbo_records: Iterable[MBORecord],
    decision_time_utc: datetime,
    config: ResistanceConfig,
    *,
    max_age_seconds: float | None = None,
) -> ResistanceField:
    if not snapshot.eligible_at(decision_time_utc):
        return ResistanceField(
            EvidenceStatus.PROTOCOL_INELIGIBLE,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            ("BOOK_NOT_CAUSALLY_ELIGIBLE",),
        )

    bids = snapshot.bids[: config.levels]
    asks = snapshot.asks[: config.levels]
    bid_depth = sum(float(x.size) for x in bids)
    ask_depth = sum(float(x.size) for x in asks)
    bid_depth_share, ask_depth_share = _shares(bid_depth, ask_depth)
    if bid_depth_share is None or ask_depth_share is None:
        return ResistanceField(
            EvidenceStatus.INSUFFICIENT_DATA,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            ("ZERO_VISIBLE_DEPTH",),
        )

    # FLOW MUST COME FROM THE SAME FEED AND THE SAME PRICE REGION AS THE DEPTH.
    # Matching on instrument alone admitted a second vendor carrying the same
    # market, which double counted provision on whichever side both vendors
    # published (measured bid_provision_share 0.8889 on a balanced book).
    # Matching on every price level admitted flow far outside the `levels`
    # window the depth term measures (a 500-lot add 1000 points away drove
    # bid_provision_share to 0.9980 on a levels=3 book).
    low = min(float(x.price) for x in bids)
    high = max(float(x.price) for x in asks)
    eligible = [
        r
        for r in mbo_records
        if r.instrument == snapshot.instrument
        and r.source == snapshot.source
        and low <= float(r.price) <= high
        and r.eligible_at(decision_time_utc, max_age_seconds=max_age_seconds)
    ]
    foreign_sources = sorted(
        {r.source for r in mbo_records
         if r.instrument == snapshot.instrument and r.source != snapshot.source}
    )
    provision = {Side.BID: 0.0, Side.ASK: 0.0}
    depletion = {Side.BID: 0.0, Side.ASK: 0.0}
    for row in eligible:
        if row.action == MBOAction.ADD:
            provision[row.side] += float(row.size)
        elif row.action in {MBOAction.CANCEL, MBOAction.TRADE}:
            depletion[row.side] += float(row.size)

    bid_prov, ask_prov = _shares(provision[Side.BID], provision[Side.ASK])
    bid_dep, ask_dep = _shares(depletion[Side.BID], depletion[Side.ASK])

    reasons: list[str] = []
    status = EvidenceStatus.UNCALIBRATED
    if foreign_sources:
        return ResistanceField(
            EvidenceStatus.PROTOCOL_INELIGIBLE,
            None, None, None,
            bid_depth_share, ask_depth_share,
            None, None, None, None,
            False,
            ("MIXED_SOURCE_FLOW_FOR_ONE_INSTRUMENT",),
        )

    needs_provision = config.provision_weight > 0
    needs_depletion = config.depletion_weight > 0
    if needs_provision and (bid_prov is None or ask_prov is None):
        reasons.append("PROVISION_FLOW_UNAVAILABLE")
    if needs_depletion and (bid_dep is None or ask_dep is None):
        reasons.append("DEPLETION_FLOW_UNAVAILABLE")

    if reasons:
        # Do not silently substitute 0 for a requested missing component.
        return ResistanceField(
            EvidenceStatus.INSUFFICIENT_DATA,
            None,
            None,
            None,
            bid_depth_share,
            ask_depth_share,
            bid_prov,
            ask_prov,
            bid_dep,
            ask_dep,
            False,
            tuple(reasons),
        )

    bid_prov_v = 0.5 if bid_prov is None else bid_prov
    ask_prov_v = 0.5 if ask_prov is None else ask_prov
    bid_dep_v = 0.5 if bid_dep is None else bid_dep
    ask_dep_v = 0.5 if ask_dep is None else ask_dep

    bid_score = _bounded_resistance(bid_depth_share, bid_prov_v, bid_dep_v, config)
    ask_score = _bounded_resistance(ask_depth_share, ask_prov_v, ask_dep_v, config)
    asymmetry = bid_score - ask_score

    return ResistanceField(
        status=status,
        bid_resistance=bid_score,
        ask_resistance=ask_score,
        directional_asymmetry=max(-1.0, min(1.0, asymmetry)),
        bid_depth_share=bid_depth_share,
        ask_depth_share=ask_depth_share,
        bid_provision_share=bid_prov,
        ask_provision_share=ask_prov,
        bid_depletion_share=bid_dep,
        ask_depletion_share=ask_dep,
        calibrated=False,
        reasons=("DESCRIPTIVE_FIELD_NOT_PREDICTIVE_PROBABILITY",),
    )
