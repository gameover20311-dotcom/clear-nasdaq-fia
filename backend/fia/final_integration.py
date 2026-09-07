# PHASE27_FINAL_INTEGRATION_V1
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import csv
import json

from .accuracy_engine import build_accuracy_assessment
from .learning_engine import build_learning_status
from .liquidity import build_liquidity_groups
from .phase22_truth import validate_truth
from .cognitive import build_cognitive_report

UTC = timezone.utc
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _ser(value: Any):
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if hasattr(value, "__dict__"):
        return value.__dict__
    return value


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _phase_manifest(phase: int) -> Dict[str, Any]:
    return _read_json(BACKEND_DIR / f"fia_backtest_phase{phase}" / f"phase{phase}_manifest.json")


def _phase24_historical() -> Dict[str, Any]:
    path = BACKEND_DIR / "fia_backtest_phase21" / "results" / "phase21_no_neutral_backtest_1y.csv"
    if not path.exists():
        return {"available": False}
    try:
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return {"available": False}

    def metric(h: int, min_conf: float):
        key = f"correct_{h}h"
        selected = []
        for r in rows:
            if str(r.get("regime") or "").upper() != "TREND":
                continue
            try:
                if float(r.get("confidence") or 0) < min_conf:
                    continue
            except Exception:
                continue
            raw = str(r.get(key) or "").strip().lower()
            if raw not in {"true", "false", "1", "0"}:
                continue
            selected.append(raw in {"true", "1"})
        return {
            "n": len(selected),
            "accuracy": round(sum(1 for x in selected if x) / len(selected) * 100.0, 2) if selected else None,
        }

    return {
        "available": True,
        "trend_confidence_65": {"4h": metric(4, 65.0), "8h": metric(8, 65.0)},
        "trend_confidence_70": {"4h": metric(4, 70.0), "8h": metric(8, 70.0)},
        "note": "Historical Phase 21 selective validation; not a promise of future accuracy.",
    }


def _phase25_status(learning: Dict[str, Any]) -> Dict[str, Any]:
    last = learning.get("last_record") or {}
    grade = str(last.get("phase25_grade") or "").upper()
    if not grade:
        return {
            "status": "AWAITING_CHART",
            "setup_grade": "—",
            "research_eligible": False,
            "confluence_score": None,
            "alignment": None,
            "completeness": None,
            "alert_level": "NONE",
            "note": "Phase 25 is installed and validated. Run chart confluence to create a live A/A+/A++ record.",
        }
    return {
        "status": "RECORDED",
        "setup_grade": grade,
        "research_eligible": str(last.get("phase25_eligible") or "").lower() in {"1", "true", "yes"},
        "confluence_score": last.get("confluence_score"),
        "alignment": last.get("confluence_alignment"),
        "completeness": last.get("confluence_completeness"),
        "alert_level": last.get("alert_level") or "NONE",
        "note": "Latest forward-recorded Phase 25 chart confluence.",
    }


async def build_final_status(hub: Any, build_forecast) -> Dict[str, Any]:
    snapshot = await hub.snapshot()
    raw = snapshot.get("data", snapshot) if isinstance(snapshot, dict) else {}
    if not isinstance(raw, dict):
        raw = {}

    forecast_input = snapshot if isinstance(snapshot, dict) and isinstance(snapshot.get("data"), dict) else {"data": raw}
    forecast = build_forecast(forecast_input)
    accuracy = build_accuracy_assessment(forecast, forecast_input)
    learning = build_learning_status()

    try:
        liquidity_groups = build_liquidity_groups(raw)
    except Exception:
        liquidity_groups = None

    truth = validate_truth(
        direction=_get(forecast, "direction"),
        thesis=_get(forecast, "thesis"),
        bullish_probability=_get(forecast, "bullish_probability", 0),
        bearish_probability=_get(forecast, "bearish_probability", 0),
        signals=_get(forecast, "signals", []) or [],
        raw=raw,
        liquidity_groups=liquidity_groups,
    )

    provider = raw.get("provider_health") or {}
    source_health = raw.get("source_health") or {}
    dxy_source = str(raw.get("dxy_source") or "")
    us10y_source = str(raw.get("us10y_source") or "")

    p24_manifest = _phase_manifest(24)
    p25_manifest = _phase_manifest(25)
    p26_manifest = _phase_manifest(26)
    phase25 = _phase25_status(learning)

    checks = {
        "phase22_truth_consistency": bool(truth.get("pass")),
        # V6.6.2 FAIL-CLOSED FIX: an ABSENT provider-health object produced
        # "UNKNOWN" != "ERROR" -> True, so a completely dataless system reported
        # overall=PASS. Absence of a health report is not evidence of health.
        "phase23_provider_health_reported": bool(provider),
        "phase23_provider_not_error": (
            bool(provider)
            and not ({t for t in str(provider.get("overall") or "").upper().replace("-", "_").split("_") if t}
                     & {"ERROR", "FAIL", "FAILED", "DOWN", "DEAD", "UNAVAILABLE"})
        ),
        "phase24_accuracy_engine": bool(accuracy.get("ok")),
        "phase24_core_frozen": p24_manifest.get("forecast_weights_changed") is False and p24_manifest.get("forecast_direction_policy_changed") is False,
        "phase25_core_frozen": p25_manifest.get("forecast_weights_changed") is False and p25_manifest.get("phase24_accuracy_logic_changed") is False,
        "phase26_core_frozen": p26_manifest.get("forecast_weights_changed") is False and p26_manifest.get("phase24_accuracy_logic_changed") is False and p26_manifest.get("phase25_confluence_logic_changed") is False,
        "phase26_forward_only": bool((learning.get("protections") or {}).get("forward_only")),
        "broker_execution_disabled": (learning.get("protections") or {}).get("broker_execution") is False,
    }
    overall = "PASS" if all(checks.values()) else "DEGRADED"
    try:
        cognitive = build_cognitive_report(forecast_input, forecast, horizon="8h", persist=False)
    except Exception as exc:
        cognitive = {"ok": False, "status": "UNAVAILABLE", "error": str(exc)}
    phase30_summary = _read_json(BACKEND_DIR / "fia_backtest_phase30" / "results" / "phase30_cognitive_replay_1y_summary.json")

    return {
        "ok": True,
        "phase": "PHASE 27",
        "module": "Final Integration & Full System Audit",
        "generated_at": datetime.now(UTC).isoformat(),
        "overall": overall,
        "checks": checks,
        "phase22": {"truth": truth},
        "phase23": {
            "provider_health": provider,
            "source_health": source_health,
            "dxy": {
                "value": raw.get("dxy_value"),
                "signal": raw.get("dxy"),
                "source": dxy_source,
                "direct": "DX-Y.NYB" in dxy_source,
                "freshness": (source_health.get("dxy") or {}).get("freshness"),
            },
            "us10y": {
                "value": raw.get("us10y_value"),
                "signal": raw.get("us10y"),
                "source": us10y_source,
                "direct": "^TNX" in us10y_source,
                "freshness": (source_health.get("us10y") or {}).get("freshness"),
            },
        },
        "phase24": accuracy,
        "phase24_historical": _phase24_historical(),
        "phase25": phase25,
        "phase26": learning,
        "phase30": {
            "live_cognitive": cognitive,
            "validation": phase30_summary,
            "market_grade_claim": (phase30_summary.get("acceptance") or {}).get("status", "WITHHELD"),
        },
        "forecast": _ser(forecast),
        "safeguards": {
            "forecast_weights_changed": False,
            "forecast_direction_policy_changed": False,
            "phase24_logic_changed": False,
            "phase25_logic_changed": False,
            "broker_execution_added": False,
            "research_only": True,
        },
    }
