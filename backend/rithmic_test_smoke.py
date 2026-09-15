from __future__ import annotations

import json
import logging
import os
from fastapi import FastAPI

# The upstream client can include login request fields in ERROR tracebacks.
# Never emit credential-bearing third-party logs from this staging service.
logging.getLogger("rithmic").setLevel(logging.CRITICAL)
logging.getLogger("async_rithmic").setLevel(logging.CRITICAL)

from nq_mbo_adapter.certification import hostile_self_test as certification_self_test
from nq_mbo_adapter.rithmic import RithmicAdapter, RithmicConnectionSpec
from nq_mbo_adapter.session_collector import (
    CAMPAIGN_END_UTC,
    CAMPAIGN_ID,
    CAMPAIGN_START_UTC,
)
from nq_mbo_adapter.session_collector_v2 import (
    ContinuousSessionCollector,
    POLICY_VERSION as COLLECTOR_POLICY_VERSION,
    hostile_self_test as collector_self_test,
    runtime_hostile_self_test,
)

CONTRACT_ID = "sha256:79fb70b98bfd448a860c68b6e65f9d6b747fe560c5c08b3a159bc32bb206c238"

app = FastAPI(
    title="CLEAR NASDAQ Rithmic Market-Truth Shadow",
    docs_url=None,
    redoc_url=None,
)


def _connection_spec() -> RithmicConnectionSpec:
    return RithmicConnectionSpec(
        contract_id=CONTRACT_ID,
        credentials_available=True,
    )


def _adapter_factory() -> RithmicAdapter:
    return RithmicAdapter(_connection_spec())


collector = ContinuousSessionCollector(_adapter_factory)


@app.get("/health")
async def health() -> dict:
    status = collector.status()
    return {
        "ok": True,
        "service": "rithmic-market-truth-shadow",
        "environment": "Rithmic Test",
        "mode": "READ_ONLY_TICKER_PLANT",
        "scope": "SHADOW_ONLY",
        "contract_id": CONTRACT_ID,
        "credentials_present": bool(os.getenv("RITHMIC_USER") and os.getenv("RITHMIC_PASSWORD")),
        "collector": status,
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
        "non_equivalence_rule": "QQQ_PROXY_MUST_NEVER_BE_LABELED_AS_NQ_MBO",
        "provider_dependence": "MASSIVE_POLYGON_DEPENDENCE_NOT_EXCLUDABLE",
        "collector": collector.status(),
    }


@app.get("/collector/status")
async def collector_status() -> dict:
    return collector.status()


@app.get("/collector/proof-contract")
async def collector_proof_contract() -> dict:
    return {
        "policy_version": COLLECTOR_POLICY_VERSION,
        "campaign_id": CAMPAIGN_ID,
        "campaign_start_utc": CAMPAIGN_START_UTC.isoformat().replace("+00:00", "Z"),
        "campaign_end_utc": CAMPAIGN_END_UTC.isoformat().replace("+00:00", "Z"),
        "scope": "SHADOW_ONLY",
        "raw_payload_persistence": False,
        "persistence": "RENDER_MANAGED_LOG_CHAIN",
        "checkpoint_interval_seconds": 30,
        "continuity_fail_closed": True,
        "promotion_rule": "NO_INTERNAL_RESULT_CAN_ALONE_AUTHORIZE_PRODUCTION_PRIMARY",
        "sequence_gap_rule": "NO_GAP_FREE_CLAIM_WITHOUT_PROVIDER_DECLARED_SEQUENCE_SEMANTICS",
        "external_audit_obligations": [
            "single_boot_id_across_full_campaign",
            "no_checkpoint_timestamp_gap_above_policy",
            "no_redeploy_during_campaign",
            "single_connection_epoch",
            "true_mbo_observed",
            "contract_identity_stable",
            "no_timestamp_regressions",
            "no_provider_venue_instrument_mismatch",
            "no_secret_material_in_logs",
        ],
    }


@app.get("/collector/selftest")
async def collector_test() -> dict:
    state_result = collector_self_test()
    runtime_result = await runtime_hostile_self_test()
    return {
        "pass": bool(state_result.get("pass") and runtime_result.get("pass")),
        "state": state_result,
        "runtime": runtime_result,
    }


@app.get("/cert/selftest")
async def cert_test() -> dict:
    return certification_self_test()


@app.get("/probe")
@app.post("/probe")
async def probe_disabled_while_collecting() -> dict:
    return {
        "status": "BLOCKED_CONTINUOUS_COLLECTOR_ACTIVE",
        "reason": "A second credentialed Rithmic session would contaminate continuity evidence.",
        "collector": collector.status(),
    }


@app.get("/cert/run")
async def cert_run_disabled_while_collecting() -> dict:
    return {
        "status": "BLOCKED_CONTINUOUS_COLLECTOR_ACTIVE",
        "reason": "Manual certification cannot compete with the frozen prospective collector session.",
        "collector": collector.status(),
    }


@app.get("/cert/reconnect")
async def reconnect_disabled_while_collecting() -> dict:
    return {
        "status": "BLOCKED_CONTINUOUS_COLLECTOR_ACTIVE",
        "reason": "Controlled reconnect testing is separated from the prospective full-session campaign.",
        "collector": collector.status(),
    }


@app.on_event("startup")
async def startup_collector() -> None:
    cert_test_result = certification_self_test()
    collector_state_test = collector_self_test()
    collector_runtime_test = await runtime_hostile_self_test()
    print("RITHMIC_CERT_SELFTEST=" + json.dumps(cert_test_result, sort_keys=True), flush=True)
    print("RITHMIC_COLLECTOR_STATE_SELFTEST=" + json.dumps(collector_state_test, sort_keys=True), flush=True)
    print("RITHMIC_COLLECTOR_RUNTIME_SELFTEST=" + json.dumps(collector_runtime_test, sort_keys=True), flush=True)
    if not cert_test_result.get("pass"):
        raise RuntimeError("Rithmic certification hostile self-test failed")
    if not collector_state_test.get("pass"):
        raise RuntimeError("Rithmic collector state hostile self-test failed")
    if not collector_runtime_test.get("pass"):
        raise RuntimeError("Rithmic collector runtime hostile self-test failed")
    await collector.start()
    print(
        "RITHMIC_COLLECTOR_STARTED="
        + json.dumps(collector.status(), sort_keys=True),
        flush=True,
    )


@app.on_event("shutdown")
async def shutdown_collector() -> None:
    await collector.stop()
