from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import FastAPI

from nq_mbo_adapter.rithmic import RithmicAdapter, RithmicConnectionSpec

CONTRACT_ID = "sha256:79fb70b98bfd448a860c68b6e65f9d6b747fe560c5c08b3a159bc32bb206c238"

app = FastAPI(title="CLEAR NASDAQ Rithmic Test Smoke", docs_url=None, redoc_url=None)

_last_result: dict = {
    "status": "NOT_RUN",
    "environment": "Rithmic Test",
    "mode": "READ_ONLY_TICKER_PLANT",
    "contract_id": CONTRACT_ID,
}
_probe_lock = asyncio.Lock()


def _public_health(adapter: RithmicAdapter) -> dict:
    health = adapter.health()
    return asdict(health)


async def run_probe(seconds: int = 20) -> dict:
    global _last_result
    async with _probe_lock:
        started = datetime.now(timezone.utc)
        adapter = RithmicAdapter(
            RithmicConnectionSpec(
                contract_id=CONTRACT_ID,
                credentials_available=True,
            )
        )
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

            # Read the adapter queue directly for this staging-only smoke probe.
            # Repeated wait_for(iterator.__anext__()) calls cancel and close an
            # async generator on timeout, which caused the previous probe to end
            # early and falsely report zero events.
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


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "service": "rithmic-test-live-smoke",
        "environment": "Rithmic Test",
        "mode": "READ_ONLY_TICKER_PLANT",
        "contract_id": CONTRACT_ID,
        "credentials_present": bool(os.getenv("RITHMIC_USER") and os.getenv("RITHMIC_PASSWORD")),
        "last_probe": _last_result,
    }


@app.get("/probe")
@app.post("/probe")
async def probe() -> dict:
    return await run_probe(20)


@app.on_event("startup")
async def startup_probe() -> None:
    async def _run_and_log() -> None:
        result = await run_probe(20)
        # Result contains no credentials; adapter health is intentionally secret-free.
        print("RITHMIC_SMOKE_RESULT=" + json.dumps(result, sort_keys=True), flush=True)

    asyncio.create_task(_run_and_log())
