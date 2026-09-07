import asyncio
# PHASE22_TRUTH_CONSISTENCY_V1
from fia.dashboard_api import build_dashboard_payload
from fia.final_integration import build_final_status
import csv
import json
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fia.providers import ProviderHub
from fia.engine import build_forecast
from fia.accuracy_engine import build_accuracy_assessment
from fia.confluence_engine import build_confluence_assessment
from fia.learning_engine import (
    attach_confluence,
    build_learning_status,
    build_research_alert,
    record_forward_forecast,
    resolve_due_forward_records,
)
from fia_backtest_phase14.backtest.engine_adapter import record_fia_forecast
from fia.liquidity import build_liquidity_map, build_liquidity_groups
from fia.chart_analysis import (
    analyze_chart,
    compare_with_fia,
)
from fia.cognitive import build_cognitive_report, build_deep_cognitive_report, verify_ledger_chain
from fia.cognitive.calibration import load_models
from fia.advanced_chart_intelligence import analyze_advanced_chart_independent
from fia.three_way_confluence import build_three_way_confluence


def compare_fia_with_gemini(fia, chart_analysis):
    """
    Compare the FIA forecast with Gemini Vision chart evidence.

    This is an evidence comparison layer, not a trading recommendation.
    """

    if not chart_analysis:
        return {
            "available": False,
            "reason": "No Gemini chart analysis available",
        }

    fia_direction = str(getattr(fia, "direction", "") or "").upper()
    gemini_direction = str(
        chart_analysis.get("direction", "") or ""
    ).upper()

    fia_bullish = getattr(fia, "bullish_probability", None)
    fia_bearish = getattr(fia, "bearish_probability", None)

    gemini_bullish = chart_analysis.get("bullish_probability")
    gemini_bearish = chart_analysis.get("bearish_probability")

    # Gemini may provide only direction/confidence.
    # Infer the missing probability conservatively when possible.
    if gemini_bullish is None and gemini_bearish is not None:
        gemini_bullish = 100.0 - float(gemini_bearish)

    if gemini_bearish is None and gemini_bullish is not None:
        gemini_bearish = 100.0 - float(gemini_bullish)

    if gemini_bullish is None:
        if gemini_direction == "BULLISH":
            gemini_bullish = 50.0
        elif gemini_direction == "BEARISH":
            gemini_bullish = 50.0

    probability_gap = None
    if fia_bullish is not None and gemini_bullish is not None:
        probability_gap = round(
            abs(float(fia_bullish) - float(gemini_bullish)), 1
        )

    direction_alignment = "UNKNOWN"

    if fia_direction and gemini_direction:
        if fia_direction == gemini_direction:
            direction_alignment = "ALIGNED"
        elif {
            fia_direction,
            gemini_direction,
        } <= {"BULLISH", "BEARISH"}:
            direction_alignment = "CONFLICT"
        else:
            direction_alignment = "PARTIAL"

    fia_confidence = float(getattr(fia, "confidence", 0.0) or 0.0)
    gemini_confidence = float(
        chart_analysis.get("confidence", 0.0) or 0.0
    )

    # Base comparison score.
    # Direction agreement is strongest, probability proximity adds support,
    # and confidence difference prevents artificially perfect agreement.
    if direction_alignment == "ALIGNED":
        alignment_score = 50.0
    elif direction_alignment == "PARTIAL":
        alignment_score = 25.0
    else:
        alignment_score = 0.0

    if probability_gap is not None:
        probability_score = max(
            0.0,
            30.0 - min(probability_gap, 30.0)
        )
    else:
        probability_score = 0.0

    confidence_gap = abs(fia_confidence - gemini_confidence)
    confidence_score = max(
        0.0,
        20.0 - min(confidence_gap, 20.0)
    )

    comparison_score = round(
        alignment_score + probability_score + confidence_score,
        1,
    )

    # Evidence-quality warning.
    fia_status = str(
        getattr(fia, "status", "") or ""
    ).upper()

    evidence_quality = (
        "DEGRADED"
        if fia_status == "DEGRADED"
        else "FULL"
        if fia_status == "LIVE"
        else "LIMITED"
    )

    if direction_alignment == "ALIGNED":
        if evidence_quality == "DEGRADED":
            assessment = (
                "Directional alignment exists, but FIA evidence quality "
                "is degraded. Review missing providers before treating "
                "the agreement as strong confirmation."
            )
        else:
            assessment = (
                "FIA and Gemini agree directionally. "
                "Review underlying evidence and probability gap."
            )
    elif direction_alignment == "CONFLICT":
        assessment = (
            "FIA and Gemini disagree directionally. "
            "Underlying evidence should be reviewed before forming a thesis."
        )
    else:
        assessment = (
            "FIA/Gemini comparison is incomplete. "
            "Review available evidence."
        )

    return {
        "available": True,
        "fia_direction": fia_direction,
        "gemini_direction": gemini_direction,
        "fia_bullish_probability": (
            round(float(fia_bullish), 1)
            if fia_bullish is not None
            else None
        ),
        "fia_bearish_probability": (
            round(float(fia_bearish), 1)
            if fia_bearish is not None
            else None
        ),
        "gemini_bullish_estimate": (
            round(float(gemini_bullish), 1)
            if gemini_bullish is not None
            else None
        ),
        "gemini_bearish_estimate": (
            round(float(gemini_bearish), 1)
            if gemini_bearish is not None
            else None
        ),
        "probability_gap": probability_gap,
        "direction_alignment": direction_alignment,
        "fia_confidence": round(fia_confidence, 1),
        "gemini_confidence": round(gemini_confidence, 1),
        "comparison_score": comparison_score,
        "evidence_quality": evidence_quality,
        "assessment": assessment,
    }


app = FastAPI(
    title="CLEAR NASDAQ — FIA",
    version="2.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


hub = ProviderHub()

BACKEND_DIR = Path(__file__).resolve().parent


def _read_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def _prediction_ledger_summary():
    path = (
        BACKEND_DIR
        / "fia_backtest_phase14"
        / "data"
        / "historical_predictions.csv"
    )
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        rows = []

    resolved = [row for row in rows if str(row.get("correct", "")).strip()]
    correct = sum(
        1
        for row in resolved
        if str(row.get("correct", "")).strip().lower()
        in {"1", "true", "yes"}
    )
    return {
        "total": len(rows),
        "resolved": len(resolved),
        "unresolved": len(rows) - len(resolved),
        "correct": correct,
        "accuracy_pct": (
            round(correct / len(resolved) * 100, 2)
            if resolved
            else None
        ),
        "latest_timestamp": rows[-1].get("timestamp") if rows else None,
    }


def _phase_statuses():
    phases = []
    for path in sorted(BACKEND_DIR.glob("fia_backtest_phase*/status.json")):
        payload = _read_json(path, {})
        phases.append({
            "phase": path.parent.name.replace("fia_backtest_", "").upper(),
            "status": payload.get("status", "AVAILABLE"),
            "detail": payload,
        })
    return phases


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "service": "CLEAR NASDAQ FIA",
        "version": "2.1.0",
        "chart_ai": True,
    }


@app.get("/api/dashboard/meta")
async def dashboard_meta():
    """Read-only operational and backtest data for the dashboard UI."""
    phase21_path = (
        BACKEND_DIR
        / "fia_backtest_phase21"
        / "results"
        / "phase21_no_neutral_backtest_1y_summary.json"
    )
    return {
        "ok": True,
        "service": "CLEAR NASDAQ FIA",
        "version": "2.1.0",
        "phase21": _read_json(phase21_path, {}),
        "prediction_ledger": _prediction_ledger_summary(),
        "phase_statuses": _phase_statuses(),
    }


@app.get("/api/provider/health")
async def provider_health():
    snapshot_data = await hub.snapshot()
    raw = snapshot_data.get("data", snapshot_data) if isinstance(snapshot_data, dict) else {}
    return {
        "ok": True,
        "provider_health": raw.get("provider_health") or {},
        "source_health": raw.get("source_health") or {},
        "dxy": {
            "value": raw.get("dxy_value"),
            "change_percent": raw.get("dxy_change_percent"),
            "signal": raw.get("dxy"),
            "source": raw.get("dxy_source"),
            "source_timestamp": raw.get("dxy_source_timestamp"),
        },
        "us10y": {
            "value": raw.get("us10y_value"),
            "change_percent": raw.get("us10y_change_percent"),
            "signal": raw.get("us10y"),
            "source": raw.get("us10y_source"),
            "source_timestamp": raw.get("us10y_source_timestamp"),
        },
    }


@app.get("/api/snapshot")
async def snapshot():
    return await hub.snapshot()


@app.get("/api/accuracy")
async def accuracy():
    snapshot_data = await hub.snapshot()
    fia_forecast = build_forecast(snapshot_data)
    return build_accuracy_assessment(fia_forecast, snapshot_data)


@app.get("/api/forecast")
async def forecast():
    snapshot_data = await hub.snapshot()
    fia_forecast = build_forecast(snapshot_data)

    # Historical prediction recorder.
    # Recorder failure must never affect the live FIA forecast.
    try:
        snapshot_payload = snapshot_data.get("data", {})
        nq_price = snapshot_payload.get("nq_futures_price")

        record_fia_forecast(
            fia_forecast,
            entry_price=nq_price,
            output_path=(
                "fia_backtest_phase14/data/"
                "historical_predictions.csv"
            ),
        )
    except Exception as exc:
        print("Prediction recorder ERROR:", repr(exc))

    # PHASE26_LEARNING_VALIDATION_V1
    # Forward-only checkpoint recorder. The first checkpoint in each time bucket
    # is frozen; repeated dashboard refreshes cannot rewrite history.
    try:
        phase26_accuracy = build_accuracy_assessment(fia_forecast, snapshot_data)
        phase26_record = record_forward_forecast(
            fia_forecast,
            snapshot_data,
            phase26_accuracy,
        )
        # Resolve due target-time outcomes asynchronously so the live forecast
        # response is not blocked by historical NQ candle retrieval.
        asyncio.create_task(resolve_due_forward_records())
    except Exception as exc:
        print("Phase26 forward recorder ERROR:", repr(exc))

    return fia_forecast


@app.get("/api/liquidity")
async def liquidity():
    snapshot_data = await hub.snapshot()

    data = snapshot_data.get("data", {})

    groups = build_liquidity_groups(data)
    levels = build_liquidity_map(data)

    return {
        "status": snapshot_data.get("status"),
        "provider": snapshot_data.get("provider"),
        "timestamp": snapshot_data.get("timestamp"),
        "groups": {
            group_name: {
                "instrument": group["instrument"],
                "current_price": group["current_price"],
                "levels": {
                    key: level.__dict__
                    for key, level in group["levels"].items()
                },
            }
            for group_name, group in groups.items()
        },
        # Backward compatibility for existing frontend.
        "levels": {
            key: level.__dict__
            for key, level in levels.items()
        },
    }


@app.post("/api/chart/analyze")
async def chart_analyze(
    file: UploadFile = File(...),
):
    allowed = {
        "image/png",
        "image/jpeg",
        "image/webp",
    }

    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only PNG, JPEG and WEBP chart images "
                "are supported."
            ),
        )

    try:
        image_bytes = await file.read()

        result = await analyze_chart(
            image_bytes=image_bytes,
            content_type=file.content_type,
            filename=file.filename or "chart",
        )

        return {
            "ok": True,
            "analysis": result,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


class ConfluenceRequest(BaseModel):
    chart_analysis: dict


class CompareRequest(BaseModel):
    user_analysis: dict


class ThreeWayConfluenceRequest(BaseModel):
    user_analysis: dict
    vision_analysis: dict


@app.post("/api/chart/advanced-analyze")
async def advanced_chart_analyze(file: UploadFile = File(...)):
    allowed = {"image/png", "image/jpeg", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG and WEBP chart images are supported.")
    try:
        image_bytes = await file.read()
        analysis = await analyze_advanced_chart_independent(
            image_bytes=image_bytes,
            content_type=file.content_type,
            filename=file.filename or "chart",
        )
        return {"ok": True, "analysis": analysis}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/confluence/three-way")
async def three_way_confluence(request: ThreeWayConfluenceRequest):
    try:
        snapshot_data = await hub.snapshot()
        fia_forecast = build_forecast(snapshot_data)
        accuracy_assessment = build_accuracy_assessment(fia_forecast, snapshot_data)
        phase25 = build_confluence_assessment(
            fia_forecast,
            accuracy_assessment,
            request.vision_analysis,
            snapshot_data,
        )
        result = build_three_way_confluence(
            fia_forecast,
            request.user_analysis,
            request.vision_analysis,
            phase25,
        )
        result["phase25"] = phase25
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/confluence")
async def confluence(request: ConfluenceRequest):
    snapshot_data = await hub.snapshot()
    fia_forecast = build_forecast(snapshot_data)
    accuracy_assessment = build_accuracy_assessment(fia_forecast, snapshot_data)
    assessment = build_confluence_assessment(
        fia_forecast,
        accuracy_assessment,
        request.chart_analysis,
        snapshot_data,
    )

    # PHASE26_LEARNING_VALIDATION_V1
    try:
        rec = record_forward_forecast(fia_forecast, snapshot_data, accuracy_assessment)
        if rec.get("ok") and rec.get("prediction_id"):
            linked = attach_confluence(
                rec["prediction_id"],
                assessment,
                accuracy_assessment,
            )
            assessment["research_alert"] = linked.get("alert") or build_research_alert(
                accuracy_assessment,
                assessment,
            )
        else:
            assessment["research_alert"] = build_research_alert(accuracy_assessment, assessment)
        asyncio.create_task(resolve_due_forward_records())
    except Exception as exc:
        assessment["research_alert"] = build_research_alert(accuracy_assessment, assessment)
        assessment["phase26_warning"] = f"Forward learning attachment unavailable: {exc}"

    return assessment


@app.get("/api/learning/status")
async def learning_status():
    # Attempt any due target-time resolutions before reporting monitoring stats.
    try:
        await resolve_due_forward_records()
    except Exception as exc:
        print("Phase26 resolver status ERROR:", repr(exc))
    return build_learning_status()


@app.post("/api/learning/resolve")
async def learning_resolve():
    changed = await resolve_due_forward_records()
    payload = build_learning_status()
    payload["resolved_fields_updated"] = changed
    return payload


@app.post("/api/analysis/compare")
async def analysis_compare(
    request: CompareRequest,
):
    try:
        snapshot_data = await hub.snapshot()
        fia_forecast = build_forecast(snapshot_data)

        if hasattr(fia_forecast, "model_dump"):
            fia_data = fia_forecast.model_dump()
        elif hasattr(fia_forecast, "dict"):
            fia_data = fia_forecast.dict()
        else:
            fia_data = dict(fia_forecast)

        chart_analysis = request.user_analysis

        comparison = compare_fia_with_gemini(
            fia=fia_forecast,
            chart_analysis=chart_analysis,
        )

        return {
            "ok": True,
            "fia": fia_data,
            "user_analysis": chart_analysis,
            "comparison": comparison,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@app.get("/api/dashboard")
async def dashboard():
    return await build_dashboard_payload(hub, build_forecast)



@app.get("/api/cognitive/forecast")
async def cognitive_forecast(deep: bool = False, horizon: str = "8h"):
    horizon = str(horizon or "8h").lower()
    if horizon not in {"4h", "8h"}:
        raise HTTPException(status_code=400, detail="horizon must be 4h or 8h")
    snapshot_data = await hub.snapshot()
    fia_forecast = build_forecast(snapshot_data)
    if deep:
        return await build_deep_cognitive_report(
            hub, snapshot_data, fia_forecast, horizon=horizon, persist=True
        )
    return build_cognitive_report(
        snapshot_data, fia_forecast, horizon=horizon, persist=True
    )


@app.get("/api/cognitive/status")
async def cognitive_status():
    summary_path = BACKEND_DIR / "fia_backtest_phase30" / "results" / "phase30_cognitive_replay_1y_summary.json"
    return {
        "ok": True,
        "architecture_version": "30.0.0-cognitive",
        "calibration": load_models(),
        "ledger_chain": verify_ledger_chain(),
        "validation": _read_json(summary_path, {}),
        "research_only": True,
        "broker_execution": False,
    }


@app.get("/api/final/status")
async def final_status():
    return await build_final_status(hub, build_forecast)

# === FIA PREMOVE ALL-IN-ONE PHASE32 ROUTE REGISTRATION ===
from fia.premove_api import install_premove_routes as _install_premove_routes
_install_premove_routes(app, hub, build_forecast)

# === FIA PHASE33 23-POINT INSTITUTIONAL PRE-MOVE ===
from fia.phase33_api import install_phase33_routes as _install_phase33_routes
_install_phase33_routes(app, hub, build_forecast)

# === FIA PHASE34 ALL-POINTS FINAL ===
from fia.phase34_api import install_phase34_routes as _install_phase34_routes
_install_phase34_routes(app, hub, build_forecast)


# === PHASE35 ONE-SHOT ROUTES ===
try:
    from fia.phase35_api import install_phase35_routes
    install_phase35_routes(app)
except Exception as phase35_route_error:
    print('PHASE35 route registration warning:', phase35_route_error)


# PHASE37 FINAL LOCK
from fia.phase37_api import install_phase37_routes
install_phase37_routes(app)
