from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import FastAPI, Query

from nq_mbo_adapter.certification import (
    CertificationPolicy,
    MarketTruthCertificate,
    hostile_self_test,
)
from nq_mbo_adapter.rithmic import RithmicAdapter, RithmicConnectionSpec

CONTRACT_ID = "sha256:79fb70b98bfd448a860c68b6e65f9d6b747fe560c5c08b3a159bc32bb206c238"

app = FastAPI(title="CLEAR NASDAQ Rithmic Market-Truth Shadow", docs_url=None, redoc_url=None)

_last_result: dict = {
    "status": "NOT_RUN",
    "environment": "Rithmic Test",
    "mode": "READ_ONLY_TICKER_PLANT",
    "contract_id": CONTRACT_ID,
}
_last_certificate: dict = {
    "status": "NOT_RUN",
    "promotion_eligible": False,
    "scope": "SHADOW_ONLY",
}
_last_reconnect: dict = {"status": "NOT_RUN"}
_probe_lock = asyncio.Lock()


def _public_health(adapter: RithmicAdapter) -> dict:
    return asdict(adapter.health())


def _connection_spec() -> RithmicConnectionSpec:
    return RithmicConnectionSpec(
        contract_id=CONTRACT_ID,
        credentials_available=True,
    )


def _optional_int_env(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _optional_float_env(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _true_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


async def _drain_to_certificate(
    adapter: RithmicAdapter,
    certificate: MarketTruthCertificate,
    seconds: float,
    *,
    max_events: int = 10000,
) -> int:
    deadline = asyncio.get_running_loop().time() + max(0.1, seconds)
    events = 0
    while asyncio.get_running_loop().time() < deadline and events < max_events:
        timeout = max(0.05, min(1.0, deadline - asyncio.get_running_loop().time()))
        try:
            event = await asyncio.wait_for(adapter._event_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            certificate.note_capability(adapter.health().capability.value)
            continue
        if event is None:
            break
        certificate.note_capability(adapter.health().capability.value)
        certificate.ingest(event)
        events += 1
    return events


async def run_probe(seconds: int = 20) -> dict:
    global _last_result
    async with _probe_lock:
        started = datetime.now(timezone.utc)
        adapter = RithmicAdapter(_connection_spec())
        result: dict = {
            "status": "STARTED",
            "started_utc": started.isoformat(),
            "environment": "Rithmic Test",
            "mode": "READ_ONLY_TICKER_PLANT",
            "contract_id": CONTRACT_ID,
            "requested_contract": "NQ",
            "event_count": 0,
            "true_mbo_event_count": 0,
            "sequence_ids": [],
        }
        try:
            await asyncio.wait_for(adapter.connect(), timeout=25)
            result["login"] = "PASS"
            result["health_after_login"] = _public_health(adapter)
            await asyncio.wait_for(adapter.subscribe("NQ"), timeout=25)
            result["subscription"] = "PASS"

            deadline = asyncio.get_running_loop().time() + max(1, min(seconds, 30))
            while asyncio.get_running_loop().time() < deadline:
                timeout = max(0.1, min(2.0, deadline - asyncio.get_running_loop().time()))
                try:
                    event = await asyncio.wait_for(adapter._event_queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    continue
                if event is None:
                    break
                result["event_count"] += 1
                if getattr(getattr(event, "capability", None), "value", None) == "TRUE_MBO":
                    result["true_mbo_event_count"] += 1
                seq = getattr(event, "sequence_id", None)
                if seq is not None and seq not in result["sequence_ids"] and len(result["sequence_ids"]) < 10:
                    result["sequence_ids"].append(seq)
                if result["event_count"] >= 50:
                    break

            result["health_after_sample"] = _public_health(adapter)
            result["status"] = "PASS" if result["login"] == "PASS" and result["subscription"] == "PASS" else "FAIL"
        except Exception as exc:
            result["status"] = "FAIL"
            result["error_type"] = type(exc).__name__
            result["error"] = str(exc)[:500]
            try:
                result["health_on_error"] = _public_health(adapter)
            except Exception:
                pass
        finally:
            try:
                await asyncio.wait_for(adapter.disconnect(), timeout=10)
            except Exception:
                pass
            result["finished_utc"] = datetime.now(timezone.utc).isoformat()
            _last_result = result
        return result


async def run_certificate(seconds: int = 30, mode: str = "SMOKE") -> dict:
    global _last_certificate
    async with _probe_lock:
        mode = mode.upper()
        bounded_seconds = max(1, min(int(seconds), 300))
        policy = CertificationPolicy(
            mode=mode,
            target_seconds=float(bounded_seconds),
            minimum_true_mbo_events=max(1, _optional_int_env("RITHMIC_CERT_MIN_TRUE_MBO_EVENTS") or 1),
            sequence_expected_step=_optional_int_env("RITHMIC_SEQUENCE_EXPECTED_STEP"),
            require_source_time_monotonicity=_true_env("RITHMIC_SOURCE_TIME_MONOTONICITY_DECLARED"),
            max_exchange_future_skew_seconds=_optional_float_env("RITHMIC_MAX_FUTURE_SKEW_SECONDS"),
            require_controlled_reconnect=_true_env("RITHMIC_REQUIRE_CONTROLLED_RECONNECT"),
            require_roll_contract_verification=_true_env("RITHMIC_REQUIRE_ROLL_VERIFICATION"),
        )
        cert = MarketTruthCertificate(policy)
        adapter = RithmicAdapter(_connection_spec())
        started = time.monotonic()
        envelope: dict = {
            "status": "STARTED",
            "scope": "SHADOW_ONLY",
            "environment": "Rithmic Test",
            "mode": mode,
            "requested_contract": "NQ",
            "contract_id": CONTRACT_ID,
        }
        try:
            await asyncio.wait_for(adapter.connect(), timeout=25)
            envelope["login"] = "PASS"
            cert.note_capability(adapter.health().capability.value)
            await asyncio.wait_for(adapter.subscribe("NQ"), timeout=25)
            envelope["subscription"] = "PASS"
            cert.note_capability(adapter.health().capability.value)
            await _drain_to_certificate(adapter, cert, bounded_seconds)
            cert.note_capability(adapter.health().capability.value)
            envelope["health_after_sample"] = _public_health(adapter)
        except Exception as exc:
            envelope["runtime_error"] = {
                "type": type(exc).__name__,
                "detail": str(exc)[:500],
            }
            cert._fail("RUNTIME_EXCEPTION")
            try:
                envelope["health_on_error"] = _public_health(adapter)
            except Exception:
                pass
        finally:
            elapsed = time.monotonic() - started
            try:
                await asyncio.wait_for(adapter.disconnect(), timeout=10)
            except Exception:
                pass

        report = cert.report(elapsed)
        envelope["certificate"] = report
        envelope["status"] = report["status"]
        envelope["promotion_eligible"] = report["promotion_eligible"]
        envelope["finished_utc"] = datetime.now(timezone.utc).isoformat()
        _last_certificate = envelope
        print("RITHMIC_MARKET_TRUTH_CERT=" + json.dumps(envelope, sort_keys=True), flush=True)
        return envelope


async def run_controlled_reconnect(sample_seconds: int = 15) -> dict:
    global _last_reconnect
    async with _probe_lock:
        result: dict = {
            "status": "STARTED",
            "scope": "SHADOW_ONLY",
            "environment": "Rithmic Test",
            "requested_contract": "NQ",
            "pre_disconnect": {},
            "post_reconnect": {},
        }
        first = RithmicAdapter(_connection_spec())
        second = RithmicAdapter(_connection_spec())
        try:
            await asyncio.wait_for(first.connect(), timeout=25)
            await asyncio.wait_for(first.subscribe("NQ"), timeout=25)
            result["pre_disconnect"]["health"] = _public_health(first)
            await asyncio.wait_for(first.disconnect(), timeout=10)
            result["disconnect"] = "PASS"

            await asyncio.wait_for(second.connect(), timeout=25)
            await asyncio.wait_for(second.subscribe("NQ"), timeout=25)
            result["reconnect"] = "PASS"

            deadline = asyncio.get_running_loop().time() + max(1, min(sample_seconds, 30))
            event_count = 0
            true_mbo = 0
            while asyncio.get_running_loop().time() < deadline and event_count < 100:
                timeout = max(0.1, min(1.0, deadline - asyncio.get_running_loop().time()))
                try:
                    event = await asyncio.wait_for(second._event_queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    continue
                if event is None:
                    break
                event_count += 1
                if getattr(getattr(event, "capability", None), "value", None) == "TRUE_MBO":
                    true_mbo += 1
            result["post_reconnect"] = {
                "health": _public_health(second),
                "event_count": event_count,
                "true_mbo_event_count": true_mbo,
            }
            if event_count > 0:
                result["status"] = "PASS"
            else:
                result["status"] = "INCONCLUSIVE_NO_POST_RECONNECT_EVENTS"
        except Exception as exc:
            result["status"] = "FAIL"
            result["error_type"] = type(exc).__name__
            result["error"] = str(exc)[:500]
        finally:
            for adapter in (first, second):
                try:
                    await asyncio.wait_for(adapter.disconnect(), timeout=10)
                except Exception:
                    pass
            result["finished_utc"] = datetime.now(timezone.utc).isoformat()
            _last_reconnect = result
            print("RITHMIC_RECONNECT_TEST=" + json.dumps(result, sort_keys=True), flush=True)
        return result


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "service": "rithmic-market-truth-shadow",
        "environment": "Rithmic Test",
        "mode": "READ_ONLY_TICKER_PLANT",
        "scope": "SHADOW_ONLY",
        "contract_id": CONTRACT_ID,
        "credentials_present": bool(os.getenv("RITHMIC_USER") and os.getenv("RITHMIC_PASSWORD")),
        "last_probe": _last_result,
        "last_certificate": _last_certificate,
        "last_reconnect": _last_reconnect,
    }


@app.get("/market-truth")
async def market_truth() -> dict:
    return {
        "scope": "SHADOW_ONLY",
        "production_primary": False,
        "priority_policy": {
            "NQ_TRUE_MBO": ["RITHMIC_CME_TRUE_MBO", "UNAVAILABLE_NO_SYNTHETIC_FALLBACK"],
            "NQ_DEPTH": ["RITHMIC_TRUE_MBO", "RITHMIC_MBP_DEPTH", "L1_ONLY"],
            "NQ_BARS": ["RITHMIC_DERIVED_AFTER_PROMOTION", "MASSIVE_NQ_IF_HEALTHY", "UNAVAILABLE"],
            "QQQ_PROXY": ["MASSIVE_POLYGON_FAMILY", "YAHOO", "UNAVAILABLE"],
            "FINNHUB": "LOWEST_DISABLED_WHILE_403",
        },
        "last_certificate": _last_certificate,
        "last_reconnect": _last_reconnect,
        "non_equivalence_rule": "QQQ_PROXY_MUST_NEVER_BE_LABELED_AS_NQ_MBO",
        "provider_dependence": "MASSIVE_POLYGON_DEPENDENCE_NOT_EXCLUDABLE",
    }


@app.get("/probe")
@app.post("/probe")
async def probe() -> dict:
    return await run_probe(20)


@app.get("/cert/selftest")
async def cert_selftest() -> dict:
    return hostile_self_test()


@app.get("/cert/run")
async def cert_run(
    seconds: int = Query(default=30, ge=1, le=300),
    mode: str = Query(default="SMOKE", pattern="^(SMOKE|FULL_SESSION)$"),
) -> dict:
    return await run_certificate(seconds, mode)


@app.get("/cert/status")
async def cert_status() -> dict:
    return _last_certificate


@app.get("/cert/reconnect")
async def cert_reconnect(seconds: int = Query(default=15, ge=1, le=30)) -> dict:
    return await run_controlled_reconnect(seconds)


@app.on_event("startup")
async def startup_probe() -> None:
    selftest = hostile_self_test()
    print("RITHMIC_CERT_SELFTEST=" + json.dumps(selftest, sort_keys=True), flush=True)
    if not selftest["pass"]:
        raise RuntimeError("Rithmic certification hostile self-test failed")

    async def _run_and_log() -> None:
        probe_result = await run_probe(20)
        print("RITHMIC_SMOKE_RESULT=" + json.dumps(probe_result, sort_keys=True), flush=True)

        smoke_cert = await run_certificate(30, "SMOKE")
        print("RITHMIC_STARTUP_SMOKE_CERT=" + json.dumps(smoke_cert, sort_keys=True), flush=True)

        reconnect_result = await run_controlled_reconnect(15)
        print("RITHMIC_STARTUP_RECONNECT=" + json.dumps(reconnect_result, sort_keys=True), flush=True)

        # Deliberately attempt a FULL_SESSION adjudication with a short sample.
        # It MUST NOT promote unless all predeclared full-session contracts are
        # actually supplied and satisfied.  This is an adversarial fail-closed
        # check, not a claim that a Globex session has elapsed.
        full_guard = await run_certificate(20, "FULL_SESSION")
        print("RITHMIC_STARTUP_FULL_GUARD=" + json.dumps(full_guard, sort_keys=True), flush=True)

    asyncio.create_task(_run_and_log())
