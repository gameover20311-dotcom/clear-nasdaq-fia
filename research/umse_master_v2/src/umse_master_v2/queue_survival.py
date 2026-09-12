from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .contracts import (
    EvidenceStatus,
    MBOAction,
    MBORecord,
    QueueSurvivalObservation,
    QueueSurvivalReport,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("decision_time_utc must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass
class _ActiveOrder:
    record: MBORecord
    remaining: float


def _closed_observation(active: _ActiveOrder, terminal: MBORecord, remaining: float) -> QueueSurvivalObservation:
    lifetime = max(0.0, (terminal.event_time_utc - active.record.event_time_utc).total_seconds())
    return QueueSurvivalObservation(
        order_id=active.record.order_id,
        side=active.record.side,
        price=active.record.price,
        entered_time_utc=active.record.event_time_utc,
        observed_until_utc=terminal.event_time_utc,
        lifetime_seconds=lifetime,
        initial_size=active.record.size,
        terminal_remaining_size=max(0.0, remaining),
        terminal_action=terminal.action,
        censored=False,
    )


def reconstruct_queue_survival(
    records: Iterable[MBORecord],
    decision_time_utc: datetime,
    *,
    max_age_seconds: float | None = None,
) -> QueueSurvivalReport:
    """Reconstruct order lifetimes from exact MBO identity only.

    This function deliberately does *not* estimate queue position or trader identity.
    Sequence gaps and missing order lineage degrade the result rather than being
    silently imputed.
    """

    decision = _utc(decision_time_utc)
    rows = tuple(r for r in records if r.eligible_at(decision, max_age_seconds=max_age_seconds))
    if not rows:
        return QueueSurvivalReport(
            status=EvidenceStatus.INSUFFICIENT_DATA,
            observations=(),
            exact_order_identity=True,
            sequence_complete=False,
            lineage_complete=False,
            trader_identity_inferred=False,
            reasons=("NO_ELIGIBLE_MBO_RECORDS",),
        )

    sources = {(r.source, r.instrument) for r in rows}
    if len(sources) != 1:
        return QueueSurvivalReport(
            status=EvidenceStatus.PROTOCOL_INELIGIBLE,
            observations=(),
            exact_order_identity=True,
            sequence_complete=False,
            lineage_complete=False,
            trader_identity_inferred=False,
            reasons=("MIXED_SOURCE_OR_INSTRUMENT_SEQUENCE_SPACE",),
        )

    ordered = tuple(sorted(rows, key=lambda r: (r.sequence, r.event_time_utc, r.provenance_id)))
    sequences = [r.sequence for r in ordered]
    sequence_unique = len(sequences) == len(set(sequences))
    sequence_complete = sequence_unique and all(b == a + 1 for a, b in zip(sequences, sequences[1:]))

    active: dict[str, _ActiveOrder] = {}
    observations: list[QueueSurvivalObservation] = []
    lineage_complete = True
    reasons: list[str] = []

    if not sequence_unique:
        reasons.append("DUPLICATE_SEQUENCE")
    elif not sequence_complete and len(sequences) > 1:
        reasons.append("SEQUENCE_GAP")

    for row in ordered:
        current = active.get(row.order_id)

        if row.action == MBOAction.ADD:
            if current is not None:
                lineage_complete = False
                reasons.append(f"DUPLICATE_ADD:{row.order_id}")
                continue
            active[row.order_id] = _ActiveOrder(record=row, remaining=float(row.size))
            continue

        if current is None:
            lineage_complete = False
            reasons.append(f"MISSING_ADD_LINEAGE:{row.order_id}")
            continue

        if row.side != current.record.side or abs(row.price - current.record.price) > 1e-12:
            lineage_complete = False
            reasons.append(f"ORDER_IDENTITY_MUTATED:{row.order_id}")
            continue

        if row.action == MBOAction.MODIFY:
            current.remaining = float(row.size)
            if current.remaining <= 0.0:
                observations.append(_closed_observation(current, row, 0.0))
                del active[row.order_id]
            continue

        if row.action in {MBOAction.CANCEL, MBOAction.TRADE}:
            quantity = float(row.size)
            if quantity <= 0.0 or quantity > current.remaining + 1e-12:
                lineage_complete = False
                reasons.append(f"INVALID_TERMINAL_QUANTITY:{row.order_id}")
                continue
            current.remaining = max(0.0, current.remaining - quantity)
            if current.remaining <= 1e-12:
                observations.append(_closed_observation(current, row, 0.0))
                del active[row.order_id]
            continue

    for order_id, current in sorted(active.items()):
        lifetime = max(0.0, (decision - current.record.event_time_utc).total_seconds())
        observations.append(
            QueueSurvivalObservation(
                order_id=order_id,
                side=current.record.side,
                price=current.record.price,
                entered_time_utc=current.record.event_time_utc,
                observed_until_utc=decision,
                lifetime_seconds=lifetime,
                initial_size=current.record.size,
                terminal_remaining_size=current.remaining,
                terminal_action=None,
                censored=True,
            )
        )

    exact = sequence_complete and lineage_complete
    status = EvidenceStatus.OBSERVED if exact else EvidenceStatus.DEGRADED
    if not observations:
        status = EvidenceStatus.INSUFFICIENT_DATA if exact else EvidenceStatus.DEGRADED
        reasons.append("NO_RECONSTRUCTABLE_ORDER_LIFETIMES")

    return QueueSurvivalReport(
        status=status,
        observations=tuple(observations),
        exact_order_identity=True,
        sequence_complete=sequence_complete,
        lineage_complete=lineage_complete,
        trader_identity_inferred=False,
        reasons=tuple(dict.fromkeys(reasons)),
    )
