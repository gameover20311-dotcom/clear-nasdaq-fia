from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    lifetime = (terminal.event_time_utc - active.record.event_time_utc).total_seconds()
    if lifetime < 0.0:
        # A negative lifetime is not a zero-second exit. It means sequence order
        # and economic/event chronology disagree, so survival time is undefined.
        raise ValueError("terminal event precedes ADD in event-time chronology")
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
    sequence_domain_complete: bool = False,
) -> QueueSurvivalReport:
    """Reconstruct order lifetimes from exact MBO identity only.

    ``sequence_domain_complete`` is an explicit protocol assertion that the
    caller supplied the complete exchange/channel sequence domain needed to
    interpret numeric gaps. Many feeds use a channel/global sequence, so an
    instrument-only subset cannot make this assertion safely.

    ``max_age_seconds`` defines an observation-window cohort; it is *not*
    applied record-by-record to an already-open lineage. We first collect every
    causally eligible row, then exclude lineages known to have entered before
    the window. This prevents a recent CANCEL/TRADE from surviving the filter
    after its older ADD was silently removed.

    The function never estimates queue position or trader identity.
    """

    decision = _utc(decision_time_utc)
    if max_age_seconds is not None and max_age_seconds < 0:
        raise ValueError("max_age_seconds must be >= 0")

    all_causal = tuple(r for r in records if r.eligible_at(decision))
    if max_age_seconds is None:
        rows = all_causal
        left_truncated_order_ids: set[str] = set()
    else:
        cutoff = decision - timedelta(seconds=max_age_seconds)
        rows = tuple(r for r in all_causal if r.event_time_utc >= cutoff)
        left_truncated_order_ids = {
            r.order_id
            for r in all_causal
            if r.action == MBOAction.ADD and r.event_time_utc < cutoff
        }

    if not rows:
        return QueueSurvivalReport(
            status=EvidenceStatus.INSUFFICIENT_DATA,
            observations=(),
            exact_order_identity=True,
            sequence_complete=False,
            lineage_complete=False,
            trader_identity_inferred=False,
            reasons=(("NO_ELIGIBLE_MBO_RECORDS_IN_WINDOW",) if max_age_seconds is not None else ("NO_ELIGIBLE_MBO_RECORDS",)),
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

    # A repeated packet is not a second market event. Left in place a duplicated
    # fill decremented the remaining size twice and closed a half-filled order
    # as a completed exit with a fabricated lifetime.
    seen_keys: set = set()
    deduped = []
    duplicate_records = 0
    for row in sorted(rows, key=lambda r: (r.sequence, r.event_time_utc, r.provenance_id)):
        key = (row.sequence, row.order_id, row.action, row.side, row.price, row.size)
        if key in seen_keys:
            duplicate_records += 1
            continue
        seen_keys.add(key)
        deduped.append(row)
    ordered = tuple(deduped)
    sequences = [r.sequence for r in ordered]
    sequence_unique = len(sequences) == len(set(sequences))
    numerically_contiguous = sequence_unique and all(b == a + 1 for a, b in zip(sequences, sequences[1:]))

    # Exchange sequence order and event-time chronology must not contradict one
    # another. A conflict commonly indicates a reset, mixed channel/domain, or
    # normalized feed that cannot support exact survival-time semantics.
    chronology_conflict = any(
        later.event_time_utc < earlier.event_time_utc
        for earlier, later in zip(ordered, ordered[1:])
    )
    if chronology_conflict:
        return QueueSurvivalReport(
            status=EvidenceStatus.PROTOCOL_INELIGIBLE,
            observations=(),
            exact_order_identity=True,
            sequence_complete=False,
            lineage_complete=False,
            trader_identity_inferred=False,
            reasons=("SEQUENCE_EVENT_TIME_ORDER_CONFLICT",),
        )

    sequence_complete = bool(sequence_domain_complete and numerically_contiguous)

    active: dict[str, _ActiveOrder] = {}
    observations: list[QueueSurvivalObservation] = []
    lineage_complete = True
    reasons: list[str] = []

    if duplicate_records:
        reasons.append("DUPLICATE_RECORDS_DROPPED")
    if not sequence_domain_complete:
        reasons.append("SEQUENCE_DOMAIN_COMPLETENESS_NOT_PROVEN")
    if not sequence_unique:
        reasons.append("DUPLICATE_SEQUENCE")
    elif sequence_domain_complete and not numerically_contiguous and len(sequences) > 1:
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
            if row.order_id in left_truncated_order_ids:
                # This order was already alive before the explicit age window.
                # Exclude the entire left-truncated lineage rather than treating
                # its recent terminal event as a fresh zero-age observation.
                reasons.append(f"LEFT_TRUNCATED_LINEAGE_EXCLUDED:{row.order_id}")
                continue
            lineage_complete = False
            reasons.append(f"MISSING_ADD_LINEAGE:{row.order_id}")
            continue

        if row.event_time_utc < current.record.event_time_utc:
            lineage_complete = False
            reasons.append(f"NEGATIVE_LIFETIME_LINEAGE:{row.order_id}")
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
        lifetime = (decision - current.record.event_time_utc).total_seconds()
        if lifetime < 0.0:
            lineage_complete = False
            reasons.append(f"ACTIVE_ORDER_FROM_FUTURE:{order_id}")
            continue
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
