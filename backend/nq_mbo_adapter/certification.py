from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json

from .integrity import SequenceContinuityGuard, SequenceContract
from .types import EventAction, FeedCapability, MBOEvent


POLICY_VERSION = "RITHMIC_MARKET_TRUTH_CERT_V1"


@dataclass(frozen=True)
class CertificationPolicy:
    mode: str = "SMOKE"
    requested_instrument: str = "NQ"
    expected_provider: str = "RITHMIC"
    expected_venue: str = "CME"
    target_seconds: float = 20.0
    minimum_true_mbo_events: int = 1
    sequence_expected_step: int | None = None
    require_source_time_monotonicity: bool = False
    max_exchange_future_skew_seconds: float | None = None
    require_controlled_reconnect: bool = False
    require_roll_contract_verification: bool = False

    def __post_init__(self) -> None:
        mode = self.mode.upper()
        if mode not in {"SMOKE", "FULL_SESSION"}:
            raise ValueError("mode must be SMOKE or FULL_SESSION")
        if self.target_seconds < 0:
            raise ValueError("target_seconds must be non-negative")
        if self.minimum_true_mbo_events < 1:
            raise ValueError("minimum_true_mbo_events must be >= 1")
        if self.sequence_expected_step is not None and self.sequence_expected_step <= 0:
            raise ValueError("sequence_expected_step must be positive when declared")
        if self.max_exchange_future_skew_seconds is not None and self.max_exchange_future_skew_seconds < 0:
            raise ValueError("max_exchange_future_skew_seconds must be non-negative")


@dataclass
class MarketTruthCertificate:
    policy: CertificationPolicy
    started_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_count: int = 0
    true_mbo_event_count: int = 0
    action_counts: dict[str, int] = field(default_factory=dict)
    resolved_contract: str | None = None
    first_exchange_utc: str | None = None
    last_exchange_utc: str | None = None
    first_receive_utc: str | None = None
    last_receive_utc: str | None = None
    max_observed_latency_ms: float | None = None
    duplicate_event_hashes: int = 0
    contract_drift_count: int = 0
    source_mismatch_count: int = 0
    venue_mismatch_count: int = 0
    instrument_mismatch_count: int = 0
    source_time_regressions: int = 0
    future_timestamp_violations: int = 0
    sequence_batch_duplicates: int = 0
    sequence_subindex_regressions: int = 0
    sequence_observations: int = 0
    sequence_failures: list[str] = field(default_factory=list)
    hard_failures: list[str] = field(default_factory=list)
    capability_transitions: list[str] = field(default_factory=list)
    reconnect_test: str = "NOT_TESTED"
    roll_contract_test: str = "NOT_TESTED"
    evidence_chain_sha256: str = field(default_factory=lambda: "0" * 64)

    _seen_hashes: set[str] = field(default_factory=set, init=False, repr=False)
    _seen_sequence_positions: set[tuple[str, int | None]] = field(default_factory=set, init=False, repr=False)
    _last_sequence_id: str | None = field(default=None, init=False, repr=False)
    _last_subindex: int | None = field(default=None, init=False, repr=False)
    _last_exchange: datetime | None = field(default=None, init=False, repr=False)
    _sequence_guard: SequenceContinuityGuard = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._sequence_guard = SequenceContinuityGuard(
            SequenceContract(expected_step=self.policy.sequence_expected_step)
        )

    @staticmethod
    def _utc_iso(dt: datetime) -> str:
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _fail(self, reason: str) -> None:
        if reason not in self.hard_failures:
            self.hard_failures.append(reason)

    def note_capability(self, capability: str) -> None:
        if not self.capability_transitions or self.capability_transitions[-1] != capability:
            self.capability_transitions.append(capability)

    def mark_controlled_reconnect(self, passed: bool) -> None:
        self.reconnect_test = "PASS" if passed else "FAIL"
        if not passed:
            self._fail("CONTROLLED_RECONNECT_FAILED")

    def mark_roll_contract_verification(self, passed: bool) -> None:
        self.roll_contract_test = "PASS" if passed else "FAIL"
        if not passed:
            self._fail("ROLL_CONTRACT_VERIFICATION_FAILED")

    def ingest(self, event: MBOEvent) -> None:
        self.event_count += 1
        if event.capability is FeedCapability.TRUE_MBO:
            self.true_mbo_event_count += 1
        else:
            self._fail("NON_TRUE_MBO_EVENT_IN_CERT_STREAM")

        if event.instrument != self.policy.requested_instrument:
            self.instrument_mismatch_count += 1
            self._fail("INSTRUMENT_MISMATCH")
        if event.source != self.policy.expected_provider:
            self.source_mismatch_count += 1
            self._fail("PROVIDER_MISMATCH")
        if event.venue != self.policy.expected_venue:
            self.venue_mismatch_count += 1
            self._fail("VENUE_MISMATCH")

        if self.resolved_contract is None:
            self.resolved_contract = event.contract
        elif event.contract != self.resolved_contract:
            self.contract_drift_count += 1
            self._fail("CONTRACT_DRIFT_WITHIN_CERT_WINDOW")

        event_hash = event.event_hash
        if event_hash in self._seen_hashes:
            self.duplicate_event_hashes += 1
            self._fail("DUPLICATE_EVENT_HASH")
        self._seen_hashes.add(event_hash)
        self.evidence_chain_sha256 = hashlib.sha256(
            (self.evidence_chain_sha256 + event_hash).encode("ascii")
        ).hexdigest()

        ex = event.exchange_timestamp.astimezone(timezone.utc)
        rx = event.receive_timestamp.astimezone(timezone.utc)
        if self.first_exchange_utc is None:
            self.first_exchange_utc = self._utc_iso(ex)
            self.first_receive_utc = self._utc_iso(rx)
        self.last_exchange_utc = self._utc_iso(ex)
        self.last_receive_utc = self._utc_iso(rx)

        latency_ms = (rx - ex).total_seconds() * 1000.0
        if self.max_observed_latency_ms is None or latency_ms > self.max_observed_latency_ms:
            self.max_observed_latency_ms = round(latency_ms, 3)

        if self.policy.max_exchange_future_skew_seconds is not None:
            if (ex - rx).total_seconds() > self.policy.max_exchange_future_skew_seconds:
                self.future_timestamp_violations += 1
                self._fail("EXCHANGE_TIMESTAMP_TOO_FAR_IN_FUTURE")

        if self.policy.require_source_time_monotonicity and self._last_exchange is not None and ex < self._last_exchange:
            self.source_time_regressions += 1
            self._fail("SOURCE_TIMESTAMP_REGRESSION")
        self._last_exchange = ex

        self.action_counts[event.action.value] = self.action_counts.get(event.action.value, 0) + 1

        if event.sequence_id is None:
            self._fail("MISSING_PROVIDER_SEQUENCE_ID")
        else:
            position = (event.sequence_id, event.sequence_subindex)
            if position in self._seen_sequence_positions:
                self.sequence_batch_duplicates += 1
                self._fail("DUPLICATE_SEQUENCE_POSITION")
            self._seen_sequence_positions.add(position)

            if event.sequence_id == self._last_sequence_id:
                if self._last_subindex is not None and event.sequence_subindex is not None:
                    if event.sequence_subindex <= self._last_subindex:
                        self.sequence_subindex_regressions += 1
                        self._fail("SEQUENCE_SUBINDEX_NOT_INCREASING")
            else:
                result = self._sequence_guard.observe(event.sequence_id)
                self.sequence_observations += 1
                if not result.ok:
                    code = result.code or "SEQUENCE_CONTINUITY_FAILURE"
                    if code != "PROVIDER_SEQUENCE_SEMANTICS_NOT_DECLARED":
                        self.sequence_failures.append(code)
                        self._fail(code)
                self._last_sequence_id = event.sequence_id
                self._last_subindex = None
            self._last_subindex = event.sequence_subindex

    def report(self, elapsed_seconds: float) -> dict:
        sequence_status = (
            "TESTED"
            if self.policy.sequence_expected_step is not None
            else "NOT_TESTED_PROVIDER_SEMANTICS_UNDECLARED"
        )
        duration_ok = elapsed_seconds >= self.policy.target_seconds
        event_count_ok = self.true_mbo_event_count >= self.policy.minimum_true_mbo_events

        blockers: list[str] = []
        if self.hard_failures:
            blockers.extend(self.hard_failures)
        if not duration_ok:
            blockers.append("TARGET_DURATION_NOT_REACHED")
        if not event_count_ok:
            blockers.append("MINIMUM_TRUE_MBO_EVENTS_NOT_REACHED")
        if self.resolved_contract is None:
            blockers.append("NO_RESOLVED_CONTRACT_EVIDENCE")

        mode = self.policy.mode.upper()
        promotion_blockers = list(blockers)
        if mode == "FULL_SESSION":
            if self.policy.sequence_expected_step is None:
                promotion_blockers.append("SEQUENCE_SEMANTICS_NOT_DECLARED")
            if not self.policy.require_source_time_monotonicity:
                promotion_blockers.append("SOURCE_TIME_ORDER_CONTRACT_NOT_DECLARED")
            if self.policy.max_exchange_future_skew_seconds is None:
                promotion_blockers.append("FUTURE_SKEW_CONTRACT_NOT_DECLARED")
            if self.policy.require_controlled_reconnect and self.reconnect_test != "PASS":
                promotion_blockers.append("CONTROLLED_RECONNECT_NOT_PROVEN")
            if self.policy.require_roll_contract_verification and self.roll_contract_test != "PASS":
                promotion_blockers.append("ROLL_CONTRACT_NOT_PROVEN")

        promotion_blockers = list(dict.fromkeys(promotion_blockers))

        if self.hard_failures:
            status = "FAIL"
        elif mode == "SMOKE" and not blockers:
            status = "SMOKE_PASS"
        elif mode == "FULL_SESSION" and not promotion_blockers:
            status = "FULL_SESSION_PASS"
        else:
            status = "INCONCLUSIVE"

        promotion_eligible = mode == "FULL_SESSION" and status == "FULL_SESSION_PASS"
        public = {
            "policy_version": POLICY_VERSION,
            "status": status,
            "promotion_eligible": promotion_eligible,
            "policy": asdict(self.policy),
            "started_utc": self.started_utc,
            "elapsed_seconds": round(float(elapsed_seconds), 3),
            "event_count": self.event_count,
            "true_mbo_event_count": self.true_mbo_event_count,
            "action_counts": dict(sorted(self.action_counts.items())),
            "resolved_contract": self.resolved_contract,
            "first_exchange_utc": self.first_exchange_utc,
            "last_exchange_utc": self.last_exchange_utc,
            "first_receive_utc": self.first_receive_utc,
            "last_receive_utc": self.last_receive_utc,
            "max_observed_latency_ms": self.max_observed_latency_ms,
            "sequence_status": sequence_status,
            "sequence_observations": self.sequence_observations,
            "sequence_failures": list(self.sequence_failures),
            "duplicate_event_hashes": self.duplicate_event_hashes,
            "contract_drift_count": self.contract_drift_count,
            "source_mismatch_count": self.source_mismatch_count,
            "venue_mismatch_count": self.venue_mismatch_count,
            "instrument_mismatch_count": self.instrument_mismatch_count,
            "source_time_regressions": self.source_time_regressions,
            "future_timestamp_violations": self.future_timestamp_violations,
            "sequence_batch_duplicates": self.sequence_batch_duplicates,
            "sequence_subindex_regressions": self.sequence_subindex_regressions,
            "capability_transitions": list(self.capability_transitions),
            "controlled_reconnect": self.reconnect_test,
            "roll_contract_verification": self.roll_contract_test,
            "evidence_chain_sha256": self.evidence_chain_sha256,
            "hard_failures": list(self.hard_failures),
            "blockers": promotion_blockers if mode == "FULL_SESSION" else blockers,
            "claims": {
                "transport_connected": "NOT_ASSERTED_BY_CERTIFICATE",
                "true_mbo_observed": self.true_mbo_event_count > 0,
                "sequence_continuity_proven": self.policy.sequence_expected_step is not None and not self.sequence_failures,
                "production_primary_approved": promotion_eligible,
            },
        }
        public["certificate_sha256"] = hashlib.sha256(
            json.dumps(public, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
        return public


def _selftest_event(
    *,
    seq: str = "1",
    subindex: int | None = 0,
    contract: str = "NQU6",
    source: str = "RITHMIC",
    venue: str = "CME",
    second: int = 0,
    order_id: str = "O1",
) -> MBOEvent:
    from decimal import Decimal
    from .types import Side

    ex = datetime(2026, 9, 15, 12, 0, second, tzinfo=timezone.utc)
    rx = datetime(2026, 9, 15, 12, 0, second, 1000, tzinfo=timezone.utc)
    return MBOEvent(
        instrument="NQ",
        contract=contract,
        venue=venue,
        source=source,
        capability=FeedCapability.TRUE_MBO,
        exchange_timestamp=ex,
        receive_timestamp=rx,
        sequence_id=seq,
        sequence_subindex=subindex,
        order_id=order_id,
        side=Side.BID,
        price=Decimal("25000.00"),
        quantity=1,
        action=EventAction.ADD,
        raw_source_hash=hashlib.sha256(f"{seq}:{subindex}:{order_id}".encode()).hexdigest(),
    )


def hostile_self_test() -> dict:
    results: dict[str, bool] = {}

    c = MarketTruthCertificate(CertificationPolicy(mode="SMOKE", target_seconds=1))
    results["zero_events_cannot_pass"] = c.report(1)["status"] != "SMOKE_PASS"

    c = MarketTruthCertificate(CertificationPolicy(mode="SMOKE", target_seconds=1))
    c.ingest(_selftest_event())
    r = c.report(1)
    results["single_true_mbo_can_smoke_pass_only"] = r["status"] == "SMOKE_PASS" and not r["promotion_eligible"]

    c = MarketTruthCertificate(CertificationPolicy(mode="SMOKE", target_seconds=1))
    e = _selftest_event()
    c.ingest(e)
    c.ingest(e)
    results["duplicate_hash_fails"] = c.report(1)["status"] == "FAIL"

    c = MarketTruthCertificate(CertificationPolicy(mode="SMOKE", target_seconds=1))
    c.ingest(_selftest_event(seq="1", contract="NQU6"))
    c.ingest(_selftest_event(seq="2", contract="NQZ6", second=1, order_id="O2"))
    results["contract_drift_fails"] = c.report(1)["status"] == "FAIL"

    c = MarketTruthCertificate(CertificationPolicy(mode="SMOKE", target_seconds=1))
    c.ingest(_selftest_event(source="OTHER"))
    results["provider_mismatch_fails"] = c.report(1)["status"] == "FAIL"

    c = MarketTruthCertificate(CertificationPolicy(mode="SMOKE", target_seconds=1))
    c.ingest(_selftest_event(venue="OTHER"))
    results["venue_mismatch_fails"] = c.report(1)["status"] == "FAIL"

    full_unknown = MarketTruthCertificate(
        CertificationPolicy(
            mode="FULL_SESSION",
            target_seconds=1,
            require_source_time_monotonicity=True,
            max_exchange_future_skew_seconds=1.0,
        )
    )
    full_unknown.ingest(_selftest_event())
    results["unknown_sequence_semantics_blocks_promotion"] = not full_unknown.report(1)["promotion_eligible"]

    clean = MarketTruthCertificate(
        CertificationPolicy(
            mode="FULL_SESSION",
            target_seconds=1,
            sequence_expected_step=1,
            require_source_time_monotonicity=True,
            max_exchange_future_skew_seconds=1.0,
        )
    )
    clean.ingest(_selftest_event(seq="1", second=0, order_id="O1"))
    clean.ingest(_selftest_event(seq="2", second=1, order_id="O2"))
    results["known_sequence_clean_path_can_pass"] = clean.report(1)["status"] == "FULL_SESSION_PASS"

    gap = MarketTruthCertificate(
        CertificationPolicy(
            mode="FULL_SESSION",
            target_seconds=1,
            sequence_expected_step=1,
            require_source_time_monotonicity=True,
            max_exchange_future_skew_seconds=1.0,
        )
    )
    gap.ingest(_selftest_event(seq="1", second=0, order_id="O1"))
    gap.ingest(_selftest_event(seq="3", second=1, order_id="O3"))
    results["sequence_gap_fails"] = gap.report(1)["status"] == "FAIL"

    batch = MarketTruthCertificate(CertificationPolicy(mode="SMOKE", target_seconds=1))
    batch.ingest(_selftest_event(seq="7", subindex=0, order_id="A"))
    batch.ingest(_selftest_event(seq="7", subindex=1, order_id="B"))
    results["same_provider_batch_with_increasing_subindex_allowed"] = batch.report(1)["status"] == "SMOKE_PASS"

    bad_batch = MarketTruthCertificate(CertificationPolicy(mode="SMOKE", target_seconds=1))
    bad_batch.ingest(_selftest_event(seq="7", subindex=1, order_id="A"))
    bad_batch.ingest(_selftest_event(seq="7", subindex=0, order_id="B"))
    results["subindex_regression_fails"] = bad_batch.report(1)["status"] == "FAIL"

    time_order = MarketTruthCertificate(
        CertificationPolicy(mode="SMOKE", target_seconds=1, require_source_time_monotonicity=True)
    )
    time_order.ingest(_selftest_event(seq="2", second=1, order_id="A"))
    time_order.ingest(_selftest_event(seq="1", second=0, order_id="B"))
    results["source_time_regression_fails"] = time_order.report(1)["status"] == "FAIL"

    return {
        "policy_version": POLICY_VERSION,
        "pass": all(results.values()),
        "passed": sum(1 for v in results.values() if v),
        "total": len(results),
        "cases": results,
    }
