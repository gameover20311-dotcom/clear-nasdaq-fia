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

    The gate is intentionally stateful.  A RESET clears sequence continuity but
    does not erase the seen-event hash set, so an exact duplicate cannot be
    silently accepted after reconnect/reset.
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
        self._seen_sequences: set[str] = set()
        self._last_exchange_time: datetime | None = None
        self._last_sequence_int: int | None = None

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

        if event.sequence_id is not None and event.sequence_id in self._seen_sequences:
            return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "DUPLICATE_SEQUENCE_ID")

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
            if event.action is not EventAction.RESET and self._last_sequence_int is not None:
                expected = self._last_sequence_int + self._sequence_contract.expected_step
                if sequence_value != expected:
                    return IntegrityResult(IntegrityStatus.FAIL, event.event_hash, "SEQUENCE_GAP_OR_OUT_OF_ORDER")
        else:
            sequence_value = None

        # State mutates only after every check passes.
        self._seen_hashes.add(event.event_hash)
        if event.sequence_id is not None:
            self._seen_sequences.add(event.sequence_id)
        self._last_exchange_time = event.exchange_timestamp

        if event.action is EventAction.RESET:
            self._last_sequence_int = None
            return IntegrityResult(IntegrityStatus.RESET_ACCEPTED, event.event_hash)

        if sequence_value is not None:
            self._last_sequence_int = sequence_value
        return IntegrityResult(IntegrityStatus.PASS, event.event_hash)
