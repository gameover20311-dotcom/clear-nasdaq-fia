"""FastAPI integration for SOL56 NEW FORWARD OOS validation."""
from __future__ import annotations

import asyncio
import os
import fcntl
import hmac
from typing import Any, Callable, Optional

from fastapi import Body, Header, HTTPException

from .forward_oos import (
    DEFAULT_ROOT,
    MIN_REPORT_N,
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


def _require_scientific_operation_secret(provided: Optional[str]) -> None:
    """Independent authorization boundary for HTTP scientific mutations.

    A normal FULL_ACCESS membership proves application access, not authority to
    create or delete scientific records.  Manual mutation routes therefore need
    a second high-entropy server secret that is never shipped to the frontend.
    The scheduled in-process collector does not use this HTTP boundary.
    """
    expected = str(os.getenv("CLEAR_NASDAQ_SCIENTIFIC_OPERATION_SECRET") or "").strip()
    if len(expected) < 32:
        raise HTTPException(status_code=503, detail="SCIENTIFIC_OPERATION_SECRET_NOT_CONFIGURED")
    supplied = str(provided or "").strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="SCIENTIFIC_OPERATION_FORBIDDEN")


def _authorize_scientific_mutation(authorization: Optional[str], operation_secret: Optional[str]) -> None:
    """Require BOTH an authenticated account and independent operation secret."""
    from fia.auth_api import require_authenticated_session

    require_authenticated_session(authorization)
    _require_scientific_operation_secret(operation_secret)


async def run_once(hub: Any, build_forecast: Callable[[dict], Any]) -> dict:
    """Run the forward collector once. Never backfills a missed forecast."""
    DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)
    collector_lock = DEFAULT_ROOT / ".collector.lock"
    with collector_lock.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"ok": True, "skipped": True,
                    "reason": "ANOTHER_FORWARD_OOS_COLLECTOR_IS_ACTIVE",
                    "report": forward_report(DEFAULT_ROOT)}
        try:
            resolution = await resolve_due_forecasts(hub, DEFAULT_ROOT)
            cp = checkpoint_state()
            lock = {"ok": True, "created": False,
                    "reason": "OUTSIDE_LIVE_CHECKPOINT_NO_BACKFILL", "checkpoint": cp}
            if cp["eligible_now"]:
                snapshot = await hub.snapshot()
                forecast = build_forecast(snapshot)
                premove = None
                try:
                    from fia.premove_watch import build_watch
                    data = snapshot.get("data") if isinstance(snapshot, dict) and isinstance(snapshot.get("data"), dict) else (snapshot or {})
                    premove = build_watch(
                        forecast,
                        snapshot,
                        {"provider_health": (data.get("provider_health") or {}),
                         "source_health": (data.get("source_health") or {})},
                        persist=False,
                    )
                except Exception as exc:
                    return {
                        "ok": False,
                        "resolution": resolution,
                        "lock": {"ok": False, "created": False,
                                 "reason": "PREMOVE_VIEW_UNAVAILABLE_CANNOT_PROVE_PARITY",
                                 "detail": "%s: %s" % (type(exc).__name__, exc)},
                        "report": forward_report(DEFAULT_ROOT),
                    }

                async def entry_lookup(contract, as_of):
                    return await explicit_contract_completed_close(
                        hub, contract, as_of, max_age_minutes=15.0
                    )

                lock = await lock_live_forecast(
                    forecast, snapshot, DEFAULT_ROOT,
                    entry_lookup=entry_lookup, premove=premove,
                )

                abstain_reasons = {
                    "PREMOVE_HORIZON_ABSTENTION_NOT_LOCKED_AS_DIRECTIONAL",
                    "PREMOVE_STATE_NOT_LOCKABLE",
                    "NO_EDGE_ABSTENTION_NOT_LOCKED_AS_DIRECTIONAL_OBSERVATION",
                }
                if (not lock.get("created")) and lock.get("reason") in abstain_reasons and premove:
                    try:
                        lock["abstention_record"] = await lock_abstention_observation(
                            forecast, snapshot, premove, DEFAULT_ROOT
                        )
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
            print("SOL56 Forward OOS worker error:", repr(exc))
        await asyncio.sleep(interval)


def _campaign_status() -> dict:
    """Separate stored history from verified/eligible scientific evidence."""
    from fia.forward_oos_durable import durability_status

    led = verify_ledger(DEFAULT_ROOT)
    rep = forward_report(DEFAULT_ROOT, audit=led)
    recs = records(DEFAULT_ROOT) or []
    storage = durability_status(DEFAULT_ROOT)
    seal = rep.get("campaign_seal") or {}
    enabled = _enabled()

    directional_n = len(recs)
    abstention_n = int(led.get("abstention_observations") or 0)
    resolved_4h = sum(1 for r in recs if r.get("4h") is not None)
    resolved_8h = sum(1 for r in recs if r.get("8h") is not None)
    integrity_valid = bool(led.get("ok") and seal.get("ok") and rep.get("ok"))
    proof_durable = storage.get("durable") is True
    operational_ok = bool(enabled and integrity_valid and proof_durable)
    eligible_4h = resolved_4h if operational_ok else 0
    eligible_8h = resolved_8h if operational_ok else 0
    metrics_available = operational_ok and min(eligible_4h, eligible_8h) >= MIN_REPORT_N

    issues = list(led.get("issues") or [])
    if not seal.get("ok"):
        issues.append("CAMPAIGN_SEAL_OR_MODEL_FINGERPRINT_INVALID")
    if rep.get("mixed_model_versions"):
        issues.append("MIXED_MODEL_FINGERPRINTS")
    if not proof_durable:
        issues.append("FORWARD_BACKUP_INCOMPLETE")
    if not enabled:
        issues.append("COLLECTOR_DISABLED")

    resolution_times = [
        (row.get(h) or {}).get("resolved_at_utc")
        for row in recs for h in ("4h", "8h")
    ]

    return {
        "ok": integrity_valid,
        "status": "READY" if operational_ok else "DEGRADED",
        "operational_ok": operational_ok,
        "checks": {
            "collector_enabled": enabled,
            "ledger_integrity": bool(led.get("ok")),
            "campaign_seal": bool(seal.get("ok")),
            "report_integrity": bool(rep.get("ok")),
            "durable_complete_proof": proof_durable,
        },
        "issues": sorted(set(issues)),
        "campaign_id": seal.get("campaign_id"),
        "model_fingerprint": (seal.get("sealed_model_fingerprint") or {}).get("digest"),
        "stored_observations_n": directional_n + abstention_n,
        "stored_directional_n": directional_n,
        "stored_abstention_n": abstention_n,
        "verified_directional_n": directional_n if integrity_valid else 0,
        "eligible_directional_n": directional_n if operational_ok else 0,
        "stored_resolved_4h_n": resolved_4h,
        "stored_resolved_8h_n": resolved_8h,
        "verified_resolved_4h_n": resolved_4h if integrity_valid else 0,
        "verified_resolved_8h_n": resolved_8h if integrity_valid else 0,
        "eligible_resolved_4h_n": eligible_4h,
        "eligible_resolved_8h_n": eligible_8h,
        "counts_basis": (
            "stored counts preserve history; verified counts require ledger+seal integrity; "
            "eligible counts additionally require complete durable proof"
        ),
        "milestones": {
            "next": MIN_REPORT_N,
            "reached": metrics_available,
            "remaining": max(0, MIN_REPORT_N - min(eligible_4h, eligible_8h)),
            "basis": "eligible verified durable completed observations in both horizons",
        },
        "last_lock_utc": max((r.get("locked_at_utc") or "" for r in recs), default="") or None,
        "last_resolution_utc": max((t for t in resolution_times if t), default=None),
        "ledger_ok": bool(led.get("ok")),
        "ledger_events": led.get("events"),
        "tamper_evident": led.get("tamper_evident"),
        "durability": storage,
        "checkpoint": checkpoint_state(),
        "metrics_available": metrics_available,
        "metrics": {"see": "/api/forward-oos/report"} if metrics_available else None,
        "metrics_withheld_reason": (
            None if metrics_available else
            "INTEGRITY_SEAL_OR_DURABILITY_FAILURE: stored records are not eligible scientific evidence."
            if not operational_ok else
            "At least %d eligible resolved observations are required in each horizon." % MIN_REPORT_N
        ),
        "base_fia": "PRODUCTION_INCUMBENT_UNCHANGED",
        "shadow_candidate": "NOT_SCORED_YET_NO_UNSEEN_ROWS",
        "predictive_edge": "NOT_PROVEN",
    }


def install_forward_oos_routes(app: Any, hub: Any, build_forecast: Callable[[dict], Any]) -> None:
    @app.get("/api/forward-oos/status")
    async def forward_oos_status():
        return {
            "enabled": _enabled(),
            "checkpoint": checkpoint_state(),
            "ledger": verify_ledger(DEFAULT_ROOT),
            "report": forward_report(DEFAULT_ROOT),
            "campaign": _campaign_status(),
        }

    @app.get("/api/forward-oos/report")
    async def forward_oos_report():
        return forward_report(DEFAULT_ROOT)

    @app.get("/api/forward-oos/verify")
    async def forward_oos_verify():
        return verify_ledger(DEFAULT_ROOT)

    @app.get("/api/forward-oos/records")
    async def forward_oos_records():
        audit = verify_ledger(DEFAULT_ROOT)
        return {
            "ok": bool(audit.get("ok")),
            "ledger": audit,
            "records_verified": bool(audit.get("ok")),
            "records": records(DEFAULT_ROOT),
        }

    @app.get("/api/forward-oos/campaign")
    async def forward_oos_campaign():
        return _campaign_status()

    @app.get("/api/forward-oos/durability")
    async def forward_oos_durability():
        from fia.forward_oos_durable import durability_status
        return durability_status(DEFAULT_ROOT)

    @app.post("/api/forward-oos/durability/test-fixture")
    async def forward_oos_durability_fixture(
        marker: str = Body(..., embed=True),
        authorization: Optional[str] = Header(default=None),
        scientific_operation_secret: Optional[str] = Header(
            default=None, alias="X-Clear-Nasdaq-Scientific-Secret"
        ),
    ):
        _authorize_scientific_mutation(authorization, scientific_operation_secret)
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
        marker: str,
        authorization: Optional[str] = Header(default=None),
        scientific_operation_secret: Optional[str] = Header(
            default=None, alias="X-Clear-Nasdaq-Scientific-Secret"
        ),
    ):
        _authorize_scientific_mutation(authorization, scientific_operation_secret)
        clean = "".join(ch for ch in str(marker) if ch.isalnum() or ch in "-_")[:64]
        from fia.forward_oos_durable import delete_test_fixture
        return delete_test_fixture(DEFAULT_ROOT, clean)

    @app.post("/api/forward-oos/run-once")
    async def forward_oos_run_once(
        authorization: Optional[str] = Header(default=None),
        scientific_operation_secret: Optional[str] = Header(
            default=None, alias="X-Clear-Nasdaq-Scientific-Secret"
        ),
    ):
        # Manual invocation is a scientific mutation command.  Membership alone
        # is deliberately insufficient; timing/no-backfill gates still apply
        # independently after authorization succeeds.
        _authorize_scientific_mutation(authorization, scientific_operation_secret)
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