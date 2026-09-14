from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from .types import EventAction, FeedCapability, MBOEvent, SourceCapabilities
from .validation import MBOValidationError, validate_event


class IntegrityStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    RESET_ACCEPTED = "RESET_ACCEPTED"


@dataclass(frozen=True)
class SequenceContract:
    """Provider-declared sequence semantics.

    `parse` converts the exact provider sequence token into an integer only when
    the vendor contract proves that such an ordering exists. `expected_step`
    must also come from the provider contract; the adapter never assumes +1.

    Providers may batch several order mutations under one sequence number.  In
    that case MBOEvent.sequence_subindex identifies the exact zero-based
    position inside the provider batch; the provider sequence itself is never
    synthetically rewritten.
    """

    contract_id: str
    parse: Callable[[str], int]
    expected_step: int

    def __post_init__(self) -> None:
        if not self.contract_id.strip():
            raise ValueError("SEQUENCE_CONTRACT_ID_REQUIRED")
        if isinstance(self.expected_step, bool) or self.expected_step <= 0:
            raise ValueError("SEQUENCE_EXPECTED_STEP_MUST_BE_POSITIVE")


@dataclass(frozen=True)
class IntegrityResult:
    status: IntegrityStatus
    event_hash: str
    reason: str | None = None


class StreamIntegrityGate:
    """Fail-closed live-stream integrity gate for one contract/subscription.

    A RESET clears continuity but not duplicate-event/sequence-position memory.
    This prevents an exact replay after reconnect from silently being accepted.
    """

    def __init__(
        self,
        *,
        capabilities: SourceCapabilities,
        expected_contract: str,
        sequence_contract: SequenceContract | None = None,
        max_receive_age_seconds: float | None = None,
    ) -> None:
        if not expected_contract.strip():
            raise ValueError("EXPECTED_CONTRACT_REQUIRED")
        if max_receive_age_seconds is not None and max_receive_age_seconds <= 0:
            raise ValueError("MAX_RECEIVE_AGE_MUST_BE_POSITIVE")
        self._capabilities = capabilities
        self._expected_contract = expected_contract
        self._sequence_contract = sequence_contract
        self._max_receive_age_seconds = max_receive_age_seconds
        self._seen_hashes: set[str] = set()
        self._seen_sequence_positions: set[tuple[str, int | None]] = set()
        self._last_exchange_time: datetime | None = None
        self._last_sequence_int: int | None = None
        self._last_sequence_subindex: int | None = None

    @property
    def ready_for_true_mbo(self) -> bool:
        if not self._capabilities.verified_true_mbo:
            return False
        return self._sequence_contract is not None

    def ingest(self, event: MBOEvent, *, now: datetime | None = None) -> IntegrityResult:
        try:
            validate_event(event, self._capabilities)
        except MBOValidationError as exc:
            return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, str(exc))

        if event.contract != self._expected_contract:
            return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "WRONG_CONTRACT")

        if event.event_hash in self._seen_hashes:
            return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "DUPLICATE_EVENT_HASH")

        if event.sequence_id is not None:
            position = (event.sequence_id, event.sequence_subindex)
            if position in self._seen_sequence_positions:
                reason = "DUPLICATE_SEQUENCE_ID" if event.sequence_subindex is None else "DUPLICATE_SEQUENCE_POSITION"
                return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, reason)

        if self._last_exchange_time is not None and event.exchange_timestamp < self._last_exchange_time:
            return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "EXCHANGE_TIMESTAMP_REVERSAL")

        if not event.replay and self._max_receive_age_seconds is not None:
            ref = now or datetime.now(timezone.utc)
            if ref.tzinfo is None or ref.utcoffset() is None:
                return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "NOW_MUST_BE_TIMEZONE_AWARE")
            age = (ref.astimezone(timezone.utc) - event.receive_timestamp.astimezone(timezone.utc)).total_seconds()
            if age < 0:
                return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "RECEIVE_TIME_IN_FUTURE")
            if age > self._max_receive_age_seconds:
                return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "STALE_EVENT")

        if event.capability is FeedCapability.TRUE_MBO:
            if self._sequence_contract is None:
                return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "SEQUENCE_CONTRACT_NOT_BOUND")
            try:
                sequence_value = self._sequence_contract.parse(str(event.sequence_id))
            except Exception:
                return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "SEQUENCE_PARSE_FAILED")
            if isinstance(sequence_value, bool) or not isinstance(sequence_value, int):
                return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "SEQUENCE_PARSE_NOT_INTEGER")

            if event.action is not EventAction.RESET:
                if self._last_sequence_int is None:
                    if event.sequence_subindex is not None and event.sequence_subindex != 0:
                        return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "BATCH_SUBINDEX_MUST_START_AT_ZERO")
                elif sequence_value == self._last_sequence_int:
                    if event.sequence_subindex is None or self._last_sequence_subindex is None:
                        return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "DUPLICATE_SEQUENCE_ID")
                    if event.sequence_subindex <= self._last_sequence_subindex:
                        return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "SEQUENCE_SUBINDEX_OUT_OF_ORDER")
                else:
                    expected = self._last_sequence_int + self._sequence_contract.expected_step
                    if sequence_value != expected:
                        return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "SEQUENCE_GAP_OR_OUT_OF_ORDER")
                    if event.sequence_subindex is not None and event.sequence_subindex != 0:
                        return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "BATCH_SUBINDEX_MUST_START_AT_ZERO")
        else:
            sequence_value = None

        # State mutates only after every check passes.
        self._seen_hashes.add(event.event_hash)
        if event.sequence_id is not None:
            self._seen_sequence_positions.add((event.sequence_id, event.sequence_subindex))
        self._last_exchange_time = event.exchange_timestamp

        if event.action is EventAction.RESET:
            self._last_sequence_int = None
            self._last_sequence_subindex = None
            return IntegrityResult(IntegrityStatus.RESET_ACCEPTED, event.event_hash)

        if sequence_value is not None:
            if sequence_value != self._last_sequence_int:
                self._last_sequence_int = sequence_value
            self._last_sequence_subindex = event.sequence_subindex
        return IntegrityResult(IntegrityStatus.PASS, event.event_hash)
