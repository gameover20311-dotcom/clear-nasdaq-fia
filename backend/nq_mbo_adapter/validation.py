from __future__ import annotations

from decimal import Decimal
import re

from .types import EventAction, FeedCapability, MBOEvent, SourceCapabilities

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class MBOValidationError(ValueError):
    pass


def validate_capability_claim(capabilities: SourceCapabilities) -> None:
    if capabilities.claimed_capability is FeedCapability.TRUE_MBO and not capabilities.verified_true_mbo:
        raise MBOValidationError("TRUE_MBO_CLAIM_NOT_PROVEN_BY_SOURCE_CAPABILITIES")


def validate_event(event: MBOEvent, capabilities: SourceCapabilities) -> None:
    validate_capability_claim(capabilities)
    if event.source != capabilities.provider:
        raise MBOValidationError("EVENT_SOURCE_CAPABILITY_PROVIDER_MISMATCH")
    if event.receive_timestamp < event.exchange_timestamp:
        raise MBOValidationError("RECEIVE_TIME_PRECEDES_EXCHANGE_TIME")
    if not event.instrument.strip() or not event.contract.strip() or not event.venue.strip():
        raise MBOValidationError("INSTRUMENT_CONTRACT_VENUE_REQUIRED")
    if event.raw_source_hash is not None and not _SHA256.fullmatch(event.raw_source_hash):
        raise MBOValidationError("RAW_SOURCE_HASH_MUST_BE_SHA256")
    if event.sequence_subindex is not None:
        if isinstance(event.sequence_subindex, bool) or event.sequence_subindex < 0:
            raise MBOValidationError("SEQUENCE_SUBINDEX_MUST_BE_NON_NEGATIVE_INTEGER")
        if event.sequence_id is None:
            raise MBOValidationError("SEQUENCE_SUBINDEX_REQUIRES_SEQUENCE_ID")

    if event.capability is FeedCapability.TRUE_MBO:
        if not capabilities.verified_true_mbo:
            raise MBOValidationError("TRUE_MBO_EVENT_FROM_UNVERIFIED_SOURCE")
        if not event.sequence_id:
            raise MBOValidationError("TRUE_MBO_SEQUENCE_ID_REQUIRED")
        if event.action is not EventAction.RESET and not event.order_id:
            raise MBOValidationError("TRUE_MBO_ORDER_ID_REQUIRED")

    if event.action in {EventAction.ADD, EventAction.MODIFY}:
        if event.side is None or event.price is None or event.quantity is None:
            raise MBOValidationError("ADD_MODIFY_REQUIRES_SIDE_PRICE_QUANTITY")
        if event.price <= Decimal("0") or event.quantity <= 0:
            raise MBOValidationError("PRICE_AND_QUANTITY_MUST_BE_POSITIVE")

    if event.depth is not None and event.depth < 0:
        raise MBOValidationError("DEPTH_MUST_BE_NON_NEGATIVE")

    if event.replay:
        # Replay may be research/calibration input, never prospective Forward-OOS proof.
        if event.capability is FeedCapability.TRUE_MBO and not capabilities.historical_replay:
            raise MBOValidationError("SOURCE_DOES_NOT_DECLARE_HISTORICAL_REPLAY")
