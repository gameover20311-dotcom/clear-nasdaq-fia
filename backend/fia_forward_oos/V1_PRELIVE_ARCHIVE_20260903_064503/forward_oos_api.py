"""FastAPI integration for SOL56 NEW FORWARD OOS validation."""
from __future__ import annotations

import asyncio
import os
import fcntl
from typing import Any, Callable, Optional

from .forward_oos import (
    DEFAULT_ROOT,
    checkpoint_state,
    explicit_contract_completed_close,
    forward_report,
    lock_live_forecast,
    records,
    resolve_due_forecasts,
    verify_ledger,
)


def _enabled() -> bool:
    return str(os.getenv("FIA_FORWARD_OOS_ENABLED", "1") or "1").strip().lower() not in {"0", "false", "no", "off"}


async def run_once(hub: Any, build_forecast: Callable[[dict], Any]) -> dict:
    """Run the forward collector once. Never backfills a missed forecast.

    A non-blocking cross-process collector mutex prevents a FastAPI worker and
    the optional macOS LaunchAgent from burning provider quota simultaneously.
    The immutable event ledger has its own stricter append lock as a second line
    of defense.
    """
    DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)
    collector_lock = DEFAULT_ROOT / ".collector.lock"
    with collector_lock.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {
                "ok": True,
                "skipped": True,
                "reason": "ANOTHER_FORWARD_OOS_COLLECTOR_IS_ACTIVE",
                "report": forward_report(DEFAULT_ROOT),
            }
        try:
            resolution = await resolve_due_forecasts(hub, DEFAULT_ROOT)
            cp = checkpoint_state()
            lock = {"ok": True, "created": False, "reason": "OUTSIDE_LIVE_CHECKPOINT_NO_BACKFILL", "checkpoint": cp}
            if cp["eligible_now"]:
                snapshot = await hub.snapshot()
                forecast = build_forecast(snapshot)

                async def entry_lookup(contract, as_of):
                    return await explicit_contract_completed_close(hub, contract, as_of, max_age_minutes=15.0)

                lock = await lock_live_forecast(
                    forecast,
                    snapshot,
                    DEFAULT_ROOT,
                    entry_lookup=entry_lookup,
                )
            return {
                "ok": bool(resolution.get("ok")) and bool(lock.get("ok")),
                "resolution": resolution,
                "lock": lock,
                "report": forward_report(DEFAULT_ROOT),
            }
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


async def _worker(app: Any, hub: Any, build_forecast: Callable[[dict], Any]) -> None:
    interval = max(30, int(os.getenv("FIA_FORWARD_OOS_POLL_SECONDS", "60") or "60"))
    while True:
        try:
            await run_once(hub, build_forecast)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Fail closed: a collector failure must not change the market model.
            print("SOL56 Forward OOS worker error:", repr(exc))
        await asyncio.sleep(interval)


def install_forward_oos_routes(app: Any, hub: Any, build_forecast: Callable[[dict], Any]) -> None:
    @app.get("/api/forward-oos/status")
    async def forward_oos_status():
        return {
            "enabled": _enabled(),
            "checkpoint": checkpoint_state(),
            "ledger": verify_ledger(DEFAULT_ROOT),
            "report": forward_report(DEFAULT_ROOT),
        }

    @app.get("/api/forward-oos/report")
    async def forward_oos_report():
        return forward_report(DEFAULT_ROOT)

    @app.get("/api/forward-oos/verify")
    async def forward_oos_verify():
        return verify_ledger(DEFAULT_ROOT)

    @app.get("/api/forward-oos/records")
    async def forward_oos_records():
        # Evidence snapshots are preserved on disk by hash. This endpoint returns
        # derived records, not a mutation surface and not raw secret-bearing env.
        return {"ok": True, "records": records(DEFAULT_ROOT)}

    @app.post("/api/forward-oos/run-once")
    async def forward_oos_run_once():
        # Manual invocation does NOT bypass the live checkpoint and therefore
        # cannot create hindsight/backfilled forecasts.
        return await run_once(hub, build_forecast)

    async def startup() -> None:
        if not _enabled():
            return
        existing: Optional[asyncio.Task] = getattr(app.state, "forward_oos_task", None)
        if existing is None or existing.done():
            app.state.forward_oos_task = asyncio.create_task(_worker(app, hub, build_forecast))

    async def shutdown() -> None:
        task: Optional[asyncio.Task] = getattr(app.state, "forward_oos_task", None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app.add_event_handler("startup", startup)
    app.add_event_handler("shutdown", shutdown)
