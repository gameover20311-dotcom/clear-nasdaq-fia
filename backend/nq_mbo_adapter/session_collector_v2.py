from __future__ import annotations

"""Runtime-hardened wrapper for the continuous session evidence collector.

V2 fixes two defects found by attacking V1 in live deployment:
1. checkpoint starvation after ``next_checkpoint`` became overdue; and
2. synthetic hostile-selftest records leaking into production-like log labels.

The underlying evidence model remains unchanged. This wrapper is shadow-only.
"""

import asyncio
import contextlib
import io
import time
from typing import Callable

from .provider import AdapterHealth
from .rithmic import RithmicAdapter
from .session_collector import (
    CHECKPOINT_INTERVAL_SECONDS,
    ContinuousSessionCollector as BaseCollector,
    hostile_self_test as base_hostile_self_test,
)

POLICY_VERSION = "RITHMIC_CONTINUOUS_SESSION_EVIDENCE_V2"


class ContinuousSessionCollector(BaseCollector):
    def __init__(
        self,
        adapter_factory: Callable[[], RithmicAdapter],
        *,
        checkpoint_interval_seconds: float = CHECKPOINT_INTERVAL_SECONDS,
    ):
        super().__init__(adapter_factory)
        if checkpoint_interval_seconds <= 0:
            raise ValueError("checkpoint_interval_seconds must be positive")
        self._checkpoint_interval_seconds = float(checkpoint_interval_seconds)

    async def _run(self) -> None:
        next_checkpoint = time.monotonic()
        reconnect_backoff = 5.0
        try:
            while not self._stop.is_set():
                now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                phase = self.phase(now)

                if phase == "FULL_SESSION_ACTIVE" and not self.campaign_initialized:
                    self._reset_campaign(now)
                if phase == "FULL_SESSION_COMPLETE":
                    self._finalize(now)
                    await asyncio.sleep(min(30.0, self._checkpoint_interval_seconds))
                    continue

                # IMPORTANT: test due-ness before applying a positive timeout
                # floor. V1 used max(0.05, negative_remaining), making this
                # branch unreachable and starving checkpoints forever.
                if time.monotonic() >= next_checkpoint:
                    self._note_capability()
                    self._emit_checkpoint(now)
                    next_checkpoint = time.monotonic() + self._checkpoint_interval_seconds
                    continue

                if self._adapter is None:
                    connected = await self._connect()
                    if not connected:
                        if phase == "FULL_SESSION_ACTIVE":
                            self._fail("CONNECTION_ATTEMPT_FAILED_DURING_FULL_SESSION")
                        await asyncio.sleep(reconnect_backoff)
                        reconnect_backoff = min(60.0, reconnect_backoff * 2.0)
                        continue
                    reconnect_backoff = 5.0

                remaining = next_checkpoint - time.monotonic()
                timeout = max(0.05, min(1.0, remaining))
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
                self._ingest(event, __import__("datetime").datetime.now(__import__("datetime").timezone.utc))
        finally:
            if self._adapter is not None:
                try:
                    await asyncio.wait_for(self._adapter.disconnect(), timeout=10)
                except Exception:
                    pass
                self._adapter = None


def hostile_self_test() -> dict:
    # V1 state tests are useful, but some intentionally call _finalize() and
    # _emit_checkpoint(). Suppress stdout so synthetic/future evidence can never
    # contaminate managed production-like logs.
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        result = base_hostile_self_test()
    result = dict(result)
    result["wrapper_policy_version"] = POLICY_VERSION
    result["synthetic_log_output_suppressed"] = True
    result["suppressed_bytes"] = len(sink.getvalue().encode("utf-8"))
    return result


async def runtime_hostile_self_test() -> dict:
    class FakeAdapter:
        def __init__(self):
            self._event_queue: asyncio.Queue = asyncio.Queue()
            self._connected = False

        async def connect(self) -> None:
            self._connected = True

        async def subscribe(self, contract: str) -> None:
            if contract != "NQ":
                raise ValueError("fake adapter is NQ-only")

        async def disconnect(self) -> None:
            self._connected = False

        def health(self) -> AdapterHealth:
            return AdapterHealth(
                provider="RITHMIC",
                connected=self._connected,
                status="CONNECTED_UNVERIFIED_CAPABILITY" if self._connected else "DISCONNECTED",
                capability="L1_ONLY",
                last_sequence_id=None,
                detail="hostile-runtime-selftest",
            )

    sink = io.StringIO()
    collector = ContinuousSessionCollector(
        lambda: FakeAdapter(),
        checkpoint_interval_seconds=0.05,
    )
    with contextlib.redirect_stdout(sink):
        await collector.start()
        await asyncio.sleep(0.18)
        status_before_stop = collector.status()
        await collector.stop()

    cases = {
        "collector_task_started": status_before_stop.get("collector_task_running") is True,
        "overdue_checkpoint_path_executes": collector.checkpoint_count >= 2,
        "preflight_scheduler_does_not_create_hard_failure": not collector.hard_failures,
        "synthetic_runtime_logs_suppressed": len(sink.getvalue()) > 0,
    }
    return {
        "policy_version": POLICY_VERSION,
        "pass": all(cases.values()),
        "passed": sum(1 for v in cases.values() if v),
        "total": len(cases),
        "checkpoint_count": collector.checkpoint_count,
        "cases": cases,
    }
