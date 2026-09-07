"""FastAPI integration for SOL56 NEW FORWARD OOS validation."""
from __future__ import annotations

import asyncio
import os
import fcntl
from typing import Any, Callable, Optional

from fastapi import Body, Header, HTTPException

from .forward_oos import (
    DEFAULT_ROOT,
    checkpoint_state,
    explicit_contract_completed_close,
    forward_report,
    lock_live_forecast,
    lock_abstention_observation,
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

                # DISPLAY/LOCK PARITY: build the SAME pre-move view the dashboard
                # renders, from the SAME forecast and snapshot, read-only
                # (persist=False so collecting never writes a watch ledger row).
                # Its per-horizon 4H/8H distributions are what gets locked.
                premove = None
                try:
                    from fia.premove_watch import build_watch
                    _data = snapshot.get("data") if isinstance(snapshot, dict) and isinstance(snapshot.get("data"), dict) else (snapshot or {})
                    premove = build_watch(
                        forecast,
                        snapshot,
                        {"provider_health": (_data.get("provider_health") or {}),
                         "source_health": (_data.get("source_health") or {})},
                        persist=False,
                    )
                except Exception as exc:
                    # Fail closed: without the displayed view we cannot prove
                    # parity, so we do not lock a directional observation.
                    return {
                        "ok": False,
                        "resolution": resolution,
                        "lock": {"ok": False, "created": False,
                                 "reason": "PREMOVE_VIEW_UNAVAILABLE_CANNOT_PROVE_PARITY",
                                 "detail": "%s: %s" % (type(exc).__name__, exc)},
                        "report": forward_report(DEFAULT_ROOT),
                    }

                async def entry_lookup(contract, as_of):
                    return await explicit_contract_completed_close(hub, contract, as_of, max_age_minutes=15.0)

                lock = await lock_live_forecast(
                    forecast,
                    snapshot,
                    DEFAULT_ROOT,
                    entry_lookup=entry_lookup,
                    premove=premove,
                )

                # V6.6.5 ABSTENTION RECORDING.
                # A refusal caused by a legitimate NO_EDGE is itself an observation
                # worth keeping. It is written as a SEPARATE non-directional record
                # so abstention frequency and post-abstention behaviour become
                # measurable, without ever entering the directional sample.
                _abstain_reasons = {
                    "PREMOVE_HORIZON_ABSTENTION_NOT_LOCKED_AS_DIRECTIONAL",
                    "PREMOVE_STATE_NOT_LOCKABLE",
                    "NO_EDGE_ABSTENTION_NOT_LOCKED_AS_DIRECTIONAL_OBSERVATION",
                }
                if (not lock.get("created")) and lock.get("reason") in _abstain_reasons and premove:
                    try:
                        abstention = await lock_abstention_observation(
                            forecast, snapshot, premove, DEFAULT_ROOT,
                        )
                        lock["abstention_record"] = abstention
                    except Exception as exc:
                        lock["abstention_record"] = {
                            "ok": False, "created": False,
                            "reason": "ABSTENTION_RECORD_FAILED",
                            "detail": "%s: %s" % (type(exc).__name__, exc),
                        }
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

    @app.get("/api/forward-oos/campaign")
    async def forward_oos_campaign():
        """Truthful campaign monitor for the 30/50/100 programme.

        Deliberately refuses to publish accuracy, Brier or calibration below the
        n=30 milestone. A win rate at n=1-5 is noise, and showing it would invite
        exactly the conclusion this campaign exists to avoid.
        """
        from fia.forward_oos_durable import durability_status
        led = verify_ledger(DEFAULT_ROOT)
        rep = forward_report(DEFAULT_ROOT)
        recs = records(DEFAULT_ROOT) or []
        directional = [r for r in recs
                       if not r.get("excluded_from_directional_statistics")]
        abstention = [r for r in recs
                      if r.get("excluded_from_directional_statistics")]
        n = len(directional)
        resolved_4h = sum(1 for r in directional if r.get("outcome_4h") is not None)
        resolved_8h = sum(1 for r in directional if r.get("outcome_8h") is not None)
        MILESTONE = 30
        return {
            "ok": True,
            "campaign_id": (rep.get("campaign_seal") or {}).get("campaign_id"),
            "model_fingerprint": ((rep.get("campaign_seal") or {})
                                  .get("sealed_model_fingerprint") or {}).get("digest"),
            "forward_oos_n": len(recs),
            "directional_n": n,
            "abstention_n": len(abstention),
            "resolved_4h_n": resolved_4h,
            "resolved_8h_n": resolved_8h,
            "milestones": {"next": MILESTONE, "reached": n >= MILESTONE,
                           "remaining": max(0, MILESTONE - n)},
            "last_lock_utc": (directional[-1].get("created_at_utc") if directional else None),
            "last_resolution_utc": (rep.get("last_resolution_utc")),
            "ledger_ok": bool(led.get("ok")),
            "ledger_events": led.get("events"),
            "tamper_evident": led.get("tamper_evident"),
            "durability": durability_status(DEFAULT_ROOT),
            "checkpoint": checkpoint_state(),
            "metrics_available": n >= MILESTONE,
            "metrics": (None if n < MILESTONE else {"see": "/api/forward-oos/report"}),
            "metrics_withheld_reason": (
                None if n >= MILESTONE else
                "n=%d directional observations. Brier, calibration and accuracy are "
                "withheld until n=%d: below that they are noise, not evidence."
                % (n, MILESTONE)),
            "base_fia": "PRODUCTION_INCUMBENT_UNCHANGED",
            "shadow_candidate": "NOT_SCORED_YET_NO_UNSEEN_ROWS",
            "predictive_edge": "NOT_PROVEN",
        }

    @app.get("/api/forward-oos/durability")
    async def forward_oos_durability():
        """What the ledger's storage actually is. Public, carries no secret."""
        from fia.forward_oos_durable import durability_status
        return durability_status(DEFAULT_ROOT)

    @app.post("/api/forward-oos/durability/test-fixture")
    async def forward_oos_durability_fixture(
        marker: str = Body(..., embed=True),
        authorization: Optional[str] = Header(default=None),
    ):
        """Write an ISOLATED TEST durability record. Authenticated.

        This is deliberately not a forecast: it carries is_test=TRUE, a
        TEST_DURABILITY_PROBE event type and a negative sequence number, so it
        can never enter the directional record or collide with a real seq. It is
        the only mechanism permitted to create or remove a fixture, and the
        delete path refuses any row that is not flagged is_test.
        """
        from fia.auth_api import _bearer, decode_session_token
        try:
            decode_session_token(_bearer(authorization))
        except Exception as exc:
            raise HTTPException(status_code=401, detail="AUTH_REQUIRED") from exc
        clean = "".join(ch for ch in str(marker) if ch.isalnum() or ch in "-_")[:64]
        if not clean:
            raise HTTPException(status_code=400, detail="INVALID_MARKER")
        from fia.forward_oos_durable import write_test_fixture
        return write_test_fixture(DEFAULT_ROOT, clean)

    @app.get("/api/forward-oos/durability/test-fixture/{marker}")
    async def forward_oos_durability_fixture_read(marker: str):
        from fia.forward_oos_durable import read_test_fixture
        clean = "".join(ch for ch in str(marker) if ch.isalnum() or ch in "-_")[:64]
        return read_test_fixture(DEFAULT_ROOT, clean)

    @app.delete("/api/forward-oos/durability/test-fixture/{marker}")
    async def forward_oos_durability_fixture_delete(
        marker: str, authorization: Optional[str] = Header(default=None),
    ):
        from fia.auth_api import _bearer, decode_session_token
        try:
            decode_session_token(_bearer(authorization))
        except Exception as exc:
            raise HTTPException(status_code=401, detail="AUTH_REQUIRED") from exc
        clean = "".join(ch for ch in str(marker) if ch.isalnum() or ch in "-_")[:64]
        from fia.forward_oos_durable import delete_test_fixture
        return delete_test_fixture(DEFAULT_ROOT, clean)

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
