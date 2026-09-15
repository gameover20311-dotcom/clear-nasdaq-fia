from __future__ import annotations

"""Continuous, shadow-only Rithmic session evidence collector.

The collector is deliberately NOT a trading component and never routes orders.
It records only derived evidence: counters, timestamps, capabilities and chained
SHA-256 hashes. Raw exchange payloads and credentials are never persisted.

Durability model on the current staging service is the managed Render log stream:
every checkpoint is emitted as one canonical JSON record with a hash link to the
previous checkpoint. A process restart changes ``boot_id``; an external audit
must treat a boot change or an excessive checkpoint-time gap as a continuity
break. The collector therefore cannot manufacture a full-session PASS after a
sleep/restart.
"""

import asyncio
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
import time
import uuid
from typing import Callable

from .rithmic import RithmicAdapter
from .types import FeedCapability, MBOEvent

UTC = timezone.utc
POLICY_VERSION = "RITHMIC_CONTINUOUS_SESSION_EVIDENCE_V1"

# Frozen prospective campaign window requested for the next complete NQ Globex
# session. KSA: 2026-09-16 01:00 -> 2026-09-17 00:00.
CAMPAIGN_ID = "RITHMIC-NQ-FULL-SESSION-20260916-KSA"
CAMPAIGN_START_UTC = datetime(2026, 9, 15, 22, 0, 0, tzinfo=UTC)
CAMPAIGN_END_UTC = datetime(2026, 9, 16, 21, 0, 0, tzinfo=UTC)
CHECKPOINT_INTERVAL_SECONDS = 30.0
MAX_CHECKPOINT_GAP_SECONDS = 75.0
MAX_CAMPAIGN_ACTIVATION_DELAY_SECONDS = 5.0
RECENT_HASH_WINDOW = 100_000


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_sha(payload: dict) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class ContinuousSessionCollector:
    def __init__(self, adapter_factory: Callable[[], RithmicAdapter]):
        self._adapter_factory = adapter_factory
        self.boot_id = uuid.uuid4().hex
        self.process_started_utc = datetime.now(UTC)
        self._process_started_monotonic = time.monotonic()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._adapter: RithmicAdapter | None = None

        self.connection_attempts = 0
        self.successful_connections = 0
        self.disconnect_or_reconnect_count = 0
        self.connection_failures = 0
        self.last_connection_error: str | None = None

        self.checkpoint_count = 0
        self.last_checkpoint_utc: datetime | None = None
        self.max_checkpoint_gap_seconds = 0.0
        self.checkpoint_chain_sha256 = "0" * 64

        self.campaign_initialized = False
        self.campaign_finalized = False
        self.campaign_activation_utc: datetime | None = None
        self.campaign_activation_delay_seconds: float | None = None
        self.event_count = 0
        self.true_mbo_event_count = 0
        self.action_counts: dict[str, int] = {}
        self.resolved_contract: str | None = None
        self.contract_drift_count = 0
        self.first_event_exchange_utc: datetime | None = None
        self.last_event_exchange_utc: datetime | None = None
        self.first_event_receive_utc: datetime | None = None
        self.last_event_receive_utc: datetime | None = None
        self.last_any_event_utc: datetime | None = None
        self.last_true_mbo_event_utc: datetime | None = None
        self.source_time_regressions = 0
        self.provider_mismatch_count = 0
        self.venue_mismatch_count = 0
        self.instrument_mismatch_count = 0
        self.sequence_position_regressions = 0
        self.duplicate_recent_event_hashes = 0
        self.event_chain_sha256 = "0" * 64
        self.capability_transitions: list[str] = []
        self.hard_failures: list[str] = []

        self._recent_hashes = deque(maxlen=RECENT_HASH_WINDOW)
        self._recent_hash_set: set[str] = set()
        self._last_sequence_tuple: tuple[int, int | None] | None = None

    def _fail(self, reason: str) -> None:
        if reason not in self.hard_failures:
            self.hard_failures.append(reason)

    def phase(self, now: datetime | None = None) -> str:
        now = now or datetime.now(UTC)
        if now < CAMPAIGN_START_UTC:
            return "PRE_FLIGHT_CANARY"
        if now < CAMPAIGN_END_UTC:
            return "FULL_SESSION_ACTIVE"
        return "FULL_SESSION_COMPLETE"

    def _reset_campaign(self, now: datetime) -> None:
        self.campaign_initialized = True
        self.campaign_finalized = False
        self.campaign_activation_utc = now
        self.campaign_activation_delay_seconds = max(
            0.0, (now - CAMPAIGN_START_UTC).total_seconds()
        )
        self.event_count = 0
        self.true_mbo_event_count = 0
        self.action_counts.clear()
        self.resolved_contract = None
        self.contract_drift_count = 0
        self.first_event_exchange_utc = None
        self.last_event_exchange_utc = None
        self.first_event_receive_utc = None
        self.last_event_receive_utc = None
        self.last_any_event_utc = None
        self.last_true_mbo_event_utc = None
        self.source_time_regressions = 0
        self.provider_mismatch_count = 0
        self.venue_mismatch_count = 0
        self.instrument_mismatch_count = 0
        self.sequence_position_regressions = 0
        self.duplicate_recent_event_hashes = 0
        self.event_chain_sha256 = "0" * 64
        self.capability_transitions.clear()
        self.hard_failures.clear()
        self._recent_hashes.clear()
        self._recent_hash_set.clear()
        self._last_sequence_tuple = None
        if self.campaign_activation_delay_seconds > MAX_CAMPAIGN_ACTIVATION_DELAY_SECONDS:
            self._fail("CAMPAIGN_ACTIVATION_LATE")

    def _note_capability(self) -> None:
        if self._adapter is None:
            capability = "DISCONNECTED"
        else:
            try:
                capability = str(self._adapter.health().capability)
            except Exception:
                capability = "HEALTH_ERROR"
        if not self.capability_transitions or self.capability_transitions[-1] != capability:
            self.capability_transitions.append(capability)

    def _remember_hash(self, event_hash: str) -> None:
        if event_hash in self._recent_hash_set:
            self.duplicate_recent_event_hashes += 1
            self._fail("DUPLICATE_EVENT_HASH_WITHIN_RECENT_WINDOW")
            return
        if len(self._recent_hashes) == RECENT_HASH_WINDOW:
            old = self._recent_hashes.popleft()
            self._recent_hash_set.discard(old)
        self._recent_hashes.append(event_hash)
        self._recent_hash_set.add(event_hash)

    def _ingest(self, event: MBOEvent, now: datetime) -> None:
        # Pre-flight events prove plumbing but must never be counted as campaign
        # evidence. This prevents hindsight/backfill contamination.
        if self.phase(now) != "FULL_SESSION_ACTIVE":
            return
        if not self.campaign_initialized:
            self._reset_campaign(now)

        self.event_count += 1
        if event.capability is FeedCapability.TRUE_MBO:
            self.true_mbo_event_count += 1
            self.last_true_mbo_event_utc = now
        else:
            self._fail("NON_TRUE_MBO_EVENT_ON_MBO_STREAM")

        if event.instrument != "NQ":
            self.instrument_mismatch_count += 1
            self._fail("INSTRUMENT_MISMATCH")
        if event.source != "RITHMIC":
            self.provider_mismatch_count += 1
            self._fail("PROVIDER_MISMATCH")
        if event.venue != "CME":
            self.venue_mismatch_count += 1
            self._fail("VENUE_MISMATCH")

        if self.resolved_contract is None:
            self.resolved_contract = event.contract
        elif event.contract != self.resolved_contract:
            self.contract_drift_count += 1
            self._fail("CONTRACT_DRIFT_WITHIN_FROZEN_SESSION")

        event_hash = event.event_hash
        self._remember_hash(event_hash)
        self.event_chain_sha256 = hashlib.sha256(
            (self.event_chain_sha256 + event_hash).encode("ascii")
        ).hexdigest()

        ex = event.exchange_timestamp.astimezone(UTC)
        rx = event.receive_timestamp.astimezone(UTC)
        if self.first_event_exchange_utc is None:
            self.first_event_exchange_utc = ex
            self.first_event_receive_utc = rx
        if self.last_event_exchange_utc is not None and ex < self.last_event_exchange_utc:
            self.source_time_regressions += 1
            self._fail("SOURCE_TIMESTAMP_REGRESSION")
        self.last_event_exchange_utc = ex
        self.last_event_receive_utc = rx
        self.last_any_event_utc = now
        self.action_counts[event.action.value] = self.action_counts.get(event.action.value, 0) + 1

        if event.sequence_id is None:
            self._fail("MISSING_PROVIDER_SEQUENCE_ID")
        else:
            try:
                seq = int(event.sequence_id)
            except (TypeError, ValueError):
                self._fail("NON_INTEGER_PROVIDER_SEQUENCE_ID")
            else:
                current = (seq, event.sequence_subindex)
                if self._last_sequence_tuple is not None:
                    last_seq, last_sub = self._last_sequence_tuple
                    if seq < last_seq:
                        self.sequence_position_regressions += 1
                        self._fail("PROVIDER_SEQUENCE_REGRESSION")
                    elif seq == last_seq:
                        if last_sub is not None and event.sequence_subindex is not None and event.sequence_subindex <= last_sub:
                            self.sequence_position_regressions += 1
                            self._fail("PROVIDER_BATCH_SUBINDEX_REGRESSION")
                self._last_sequence_tuple = current

    def _snapshot(self, now: datetime) -> dict:
        health: dict
        if self._adapter is None:
            health = {
                "connected": False,
                "status": "NO_ADAPTER",
                "capability": "DISCONNECTED",
                "last_sequence_id": None,
            }
        else:
            try:
                h = self._adapter.health()
                health = {
                    "connected": bool(h.connected),
                    "status": h.status,
                    "capability": str(h.capability),
                    "last_sequence_id": h.last_sequence_id,
                }
            except Exception as exc:
                health = {
                    "connected": False,
                    "status": f"HEALTH_ERROR:{type(exc).__name__}",
                    "capability": "UNKNOWN",
                    "last_sequence_id": None,
                }

        seconds_since_last_event = (
            None if self.last_any_event_utc is None else round((now - self.last_any_event_utc).total_seconds(), 3)
        )
        seconds_since_last_true_mbo = (
            None if self.last_true_mbo_event_utc is None else round((now - self.last_true_mbo_event_utc).total_seconds(), 3)
        )
        snapshot = {
            "policy_version": POLICY_VERSION,
            "campaign_id": CAMPAIGN_ID,
            "campaign_start_utc": _iso(CAMPAIGN_START_UTC),
            "campaign_end_utc": _iso(CAMPAIGN_END_UTC),
            "phase": self.phase(now),
            "scope": "SHADOW_ONLY",
            "production_primary": False,
            "boot_id": self.boot_id,
            "process_started_utc": _iso(self.process_started_utc),
            "observed_utc": _iso(now),
            "process_uptime_seconds": round(time.monotonic() - self._process_started_monotonic, 3),
            "connection_attempts": self.connection_attempts,
            "successful_connections": self.successful_connections,
            "disconnect_or_reconnect_count": self.disconnect_or_reconnect_count,
            "connection_failures": self.connection_failures,
            "health": health,
            "checkpoint_count": self.checkpoint_count,
            "max_checkpoint_gap_seconds": round(self.max_checkpoint_gap_seconds, 3),
            "campaign_initialized": self.campaign_initialized,
            "campaign_finalized": self.campaign_finalized,
            "campaign_activation_utc": _iso(self.campaign_activation_utc),
            "campaign_activation_delay_seconds": self.campaign_activation_delay_seconds,
            "event_count": self.event_count,
            "true_mbo_event_count": self.true_mbo_event_count,
            "action_counts": dict(sorted(self.action_counts.items())),
            "resolved_contract": self.resolved_contract,
            "contract_drift_count": self.contract_drift_count,
            "first_event_exchange_utc": _iso(self.first_event_exchange_utc),
            "last_event_exchange_utc": _iso(self.last_event_exchange_utc),
            "first_event_receive_utc": _iso(self.first_event_receive_utc),
            "last_event_receive_utc": _iso(self.last_event_receive_utc),
            "seconds_since_last_event": seconds_since_last_event,
            "seconds_since_last_true_mbo": seconds_since_last_true_mbo,
            "source_time_regressions": self.source_time_regressions,
            "provider_mismatch_count": self.provider_mismatch_count,
            "venue_mismatch_count": self.venue_mismatch_count,
            "instrument_mismatch_count": self.instrument_mismatch_count,
            "sequence_position_regressions": self.sequence_position_regressions,
            "duplicate_recent_event_hashes": self.duplicate_recent_event_hashes,
            "duplicate_detection_scope": f"recent_{RECENT_HASH_WINDOW}_events",
            "event_chain_sha256": self.event_chain_sha256,
            "capability_transitions": list(self.capability_transitions),
            "hard_failures": list(self.hard_failures),
            "sequence_gap_semantics": "NOT_CLAIMED_PROVIDER_STEP_NOT_DECLARED",
            "persistence_backend": "RENDER_MANAGED_LOG_CHAIN",
            "raw_market_payloads_persisted": False,
            "credentials_persisted": False,
        }
        return snapshot

    def _emit_checkpoint(self, now: datetime, label: str = "RITHMIC_COLLECTOR_CHECKPOINT") -> dict:
        if self.last_checkpoint_utc is not None:
            gap = (now - self.last_checkpoint_utc).total_seconds()
            self.max_checkpoint_gap_seconds = max(self.max_checkpoint_gap_seconds, gap)
            if self.phase(now) == "FULL_SESSION_ACTIVE" and gap > MAX_CHECKPOINT_GAP_SECONDS:
                self._fail("CHECKPOINT_CONTINUITY_GAP")
        self.last_checkpoint_utc = now
        self.checkpoint_count += 1
        payload = self._snapshot(now)
        payload["previous_checkpoint_sha256"] = self.checkpoint_chain_sha256
        payload["checkpoint_sha256"] = _canonical_sha(payload)
        self.checkpoint_chain_sha256 = payload["checkpoint_sha256"]
        print(label + "=" + json.dumps(payload, sort_keys=True), flush=True)
        return payload

    def _finalize(self, now: datetime) -> dict:
        if self.campaign_finalized:
            return self._snapshot(now)
        self.campaign_finalized = True
        if not self.campaign_initialized:
            self._fail("CAMPAIGN_NEVER_ACTIVATED")
        if self.event_count <= 0:
            self._fail("NO_MBO_EVENTS_IN_FULL_SESSION")
        if self.true_mbo_event_count <= 0:
            self._fail("NO_TRUE_MBO_EVENTS_IN_FULL_SESSION")
        if self.max_checkpoint_gap_seconds > MAX_CHECKPOINT_GAP_SECONDS:
            self._fail("CHECKPOINT_CONTINUITY_GAP")
        if self.successful_connections != 1:
            self._fail("SESSION_DID_NOT_REMAIN_ON_SINGLE_CONNECTION_EPOCH")
        final = self._emit_checkpoint(now, label="RITHMIC_FULL_SESSION_FINAL")
        final["external_audit_required"] = [
            "verify_no_boot_id_change_across_managed_logs",
            "verify_no_render_log_timestamp_gap_above_policy",
            "verify_service_was_not_redeployed_during_campaign",
            "verify_provider_sequence_step_semantics_separately_before_claiming_gap_free_sequence",
        ]
        final["promotion_eligible_internal"] = not self.hard_failures
        # Internal status can never alone authorize production. External log
        # continuity and provider-sequence semantics remain separate obligations.
        final["production_primary_approved"] = False
        return final

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="rithmic-continuous-session-collector")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=15)
            except Exception:
                self._task.cancel()
        self._task = None

    async def _connect(self) -> bool:
        self.connection_attempts += 1
        adapter = self._adapter_factory()
        try:
            await asyncio.wait_for(adapter.connect(), timeout=25)
            await asyncio.wait_for(adapter.subscribe("NQ"), timeout=25)
        except Exception as exc:
            self.connection_failures += 1
            self.last_connection_error = type(exc).__name__
            try:
                await asyncio.wait_for(adapter.disconnect(), timeout=5)
            except Exception:
                pass
            return False
        self._adapter = adapter
        self.successful_connections += 1
        if self.successful_connections > 1:
            self.disconnect_or_reconnect_count += 1
            if self.phase() == "FULL_SESSION_ACTIVE":
                self._fail("UNEXPECTED_RECONNECT_DURING_FULL_SESSION")
        self.last_connection_error = None
        self._note_capability()
        return True

    async def _run(self) -> None:
        next_checkpoint = time.monotonic()
        reconnect_backoff = 5.0
        try:
            while not self._stop.is_set():
                now = datetime.now(UTC)
                phase = self.phase(now)
                if phase == "FULL_SESSION_ACTIVE" and not self.campaign_initialized:
                    self._reset_campaign(now)
                if phase == "FULL_SESSION_COMPLETE":
                    self._finalize(now)
                    await asyncio.sleep(30)
                    continue

                if self._adapter is None:
                    connected = await self._connect()
                    if not connected:
                        if phase == "FULL_SESSION_ACTIVE":
                            self._fail("CONNECTION_ATTEMPT_FAILED_DURING_FULL_SESSION")
                        if time.monotonic() >= next_checkpoint:
                            self._emit_checkpoint(datetime.now(UTC))
                            next_checkpoint = time.monotonic() + CHECKPOINT_INTERVAL_SECONDS
                        await asyncio.sleep(reconnect_backoff)
                        reconnect_backoff = min(60.0, reconnect_backoff * 2.0)
                        continue
                    reconnect_backoff = 5.0

                timeout = max(0.05, min(1.0, next_checkpoint - time.monotonic()))
                if timeout <= 0:
                    self._note_capability()
                    self._emit_checkpoint(datetime.now(UTC))
                    next_checkpoint = time.monotonic() + CHECKPOINT_INTERVAL_SECONDS
                    continue

                try:
                    event = await asyncio.wait_for(self._adapter._event_queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    continue
                except Exception as exc:
                    self.last_connection_error = type(exc).__name__
                    if phase == "FULL_SESSION_ACTIVE":
                        self._fail("EVENT_QUEUE_RUNTIME_EXCEPTION")
                    try:
                        await self._adapter.disconnect()
                    except Exception:
                        pass
                    self._adapter = None
                    continue

                if event is None:
                    if phase == "FULL_SESSION_ACTIVE":
                        self._fail("UNEXPECTED_EVENT_STREAM_END")
                    self._adapter = None
                    continue
                self._note_capability()
                self._ingest(event, datetime.now(UTC))
        finally:
            if self._adapter is not None:
                try:
                    await asyncio.wait_for(self._adapter.disconnect(), timeout=10)
                except Exception:
                    pass
                self._adapter = None

    def status(self) -> dict:
        now = datetime.now(UTC)
        payload = self._snapshot(now)
        payload["previous_checkpoint_sha256"] = self.checkpoint_chain_sha256
        payload["collector_task_running"] = bool(self._task and not self._task.done())
        return payload


def hostile_self_test() -> dict:
    """Pure-state hostile checks for fail-closed campaign policy."""
    from decimal import Decimal
    from .types import EventAction, Side

    class DummyAdapter:
        def health(self):
            class H:
                connected = True
                status = "CONNECTED_TRUE_MBO_VERIFIED"
                capability = "TRUE_MBO"
                last_sequence_id = "1"
            return H()

    def event(seq: str = "1", sub: int = 0, contract: str = "NQZ6", second: int = 0) -> MBOEvent:
        ex = CAMPAIGN_START_UTC.replace(second=second)
        return MBOEvent(
            instrument="NQ",
            contract=contract,
            venue="CME",
            source="RITHMIC",
            capability=FeedCapability.TRUE_MBO,
            exchange_timestamp=ex,
            receive_timestamp=ex,
            sequence_id=seq,
            sequence_subindex=sub,
            order_id=f"O-{seq}-{sub}",
            side=Side.BID,
            price=Decimal("25000"),
            quantity=1,
            action=EventAction.ADD,
            raw_source_hash=hashlib.sha256(f"raw:{seq}:{sub}".encode()).hexdigest(),
        )

    cases: dict[str, bool] = {}
    c = ContinuousSessionCollector(lambda: DummyAdapter())
    pre = CAMPAIGN_START_UTC.replace(hour=21, minute=59)
    c._ingest(event(), pre)
    cases["preflight_event_not_counted"] = c.event_count == 0

    c = ContinuousSessionCollector(lambda: DummyAdapter())
    c._adapter = DummyAdapter()
    c._reset_campaign(CAMPAIGN_START_UTC)
    c._ingest(event(seq="1", sub=0), CAMPAIGN_START_UTC)
    c._ingest(event(seq="1", sub=1, second=1), CAMPAIGN_START_UTC.replace(second=1))
    cases["valid_batch_positions_accepted"] = not c.hard_failures and c.event_count == 2

    c._ingest(event(seq="1", sub=1, second=2), CAMPAIGN_START_UTC.replace(second=2))
    cases["duplicate_or_regressed_position_fails"] = bool(c.hard_failures)

    c = ContinuousSessionCollector(lambda: DummyAdapter())
    c._adapter = DummyAdapter()
    c._reset_campaign(CAMPAIGN_START_UTC)
    c._ingest(event(seq="2", contract="NQZ6"), CAMPAIGN_START_UTC)
    c._ingest(event(seq="3", contract="NQH7", second=1), CAMPAIGN_START_UTC.replace(second=1))
    cases["contract_drift_fails"] = "CONTRACT_DRIFT_WITHIN_FROZEN_SESSION" in c.hard_failures

    c = ContinuousSessionCollector(lambda: DummyAdapter())
    c._adapter = DummyAdapter()
    c._reset_campaign(CAMPAIGN_START_UTC)
    c.last_checkpoint_utc = CAMPAIGN_START_UTC
    c._emit_checkpoint(CAMPAIGN_START_UTC.replace(minute=2))
    cases["heartbeat_gap_fails"] = "CHECKPOINT_CONTINUITY_GAP" in c.hard_failures

    c = ContinuousSessionCollector(lambda: DummyAdapter())
    final = c._finalize(CAMPAIGN_END_UTC)
    cases["empty_session_cannot_pass"] = (
        "NO_TRUE_MBO_EVENTS_IN_FULL_SESSION" in c.hard_failures
        and final.get("production_primary_approved") is False
    )

    c = ContinuousSessionCollector(lambda: DummyAdapter())
    c._adapter = DummyAdapter()
    c._reset_campaign(CAMPAIGN_START_UTC)
    c._ingest(event(), CAMPAIGN_START_UTC)
    c.successful_connections = 2
    c._finalize(CAMPAIGN_END_UTC)
    cases["multiple_connection_epochs_block_internal_eligibility"] = (
        "SESSION_DID_NOT_REMAIN_ON_SINGLE_CONNECTION_EPOCH" in c.hard_failures
    )

    return {
        "policy_version": POLICY_VERSION,
        "pass": all(cases.values()),
        "passed": sum(1 for value in cases.values() if value),
        "total": len(cases),
        "cases": cases,
    }
