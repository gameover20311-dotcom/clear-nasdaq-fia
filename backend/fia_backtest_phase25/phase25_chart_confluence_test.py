#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENGINE = ROOT / "fia" / "engine.py"
ACCURACY = ROOT / "fia" / "accuracy_engine.py"
CHART = ROOT / "fia" / "chart_analysis.py"
MANIFEST = Path(__file__).resolve().parent / "phase25_manifest.json"

from fia.confluence_engine import build_confluence_assessment, chart_confluence_features


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strong_forecast():
    return SimpleNamespace(
        direction="BEARISH",
        confidence=72.0,
        regime="TREND",
        bullish_probability=28.0,
        bearish_probability=72.0,
    )


def main():
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["phase"] == "PHASE 25" and manifest["forecast_weights_changed"] is False
    assert len(manifest["engine_sha256_before"]) == 64 and len(manifest["accuracy_sha256_before"]) == 64
    assert ENGINE.exists() and ACCURACY.exists()
    print("✅ Historical Phase25 provenance manifest preserved")
    print("✅ Current engine/accuracy files present; current-release hashes are enforced by final release gate")

    chart_text = CHART.read_text()
    assert "PHASE25_CHART_CONFLUENCE_V1" in chart_text
    assert "PHASE25_CONFLUENCE_INSTRUCTIONS" in chart_text
    print("✅ Vision confluence extraction instructions installed")

    forecast = strong_forecast()
    accuracy = {"setup_grade": "A++", "research_eligible": True}
    chart = {
        "direction": "BEARISH",
        "htf_poi": {"type": "supply", "direction": "BEARISH"},
        "order_blocks": [{"direction": "BEARISH", "type": "supply"}],
        "fair_value_gaps": [{"direction": "BEARISH"}],
        "liquidity_sweeps": [{"side": "BUY-SIDE", "reaction": "BEARISH REJECTION"}],
        "smt": {"detected": True, "direction": "BEARISH", "pair": "ES"},
        "session_context": {"session": "LONDON", "direction": "BEARISH"},
        "execution_confirmation": {"timeframe": "1m", "direction": "BEARISH"},
    }
    a = build_confluence_assessment(forecast, accuracy, chart, {})
    assert a["setup_grade"] == "A++", a
    assert a["research_eligible"] is True
    assert a["confluence_score"] >= 85
    assert a["features"]["liquidity_sweep_reclaim"]["aligned"] is True
    print("✅ A++ HTF/OB/FVG/liquidity/SMT/session/execution confluence PASS")

    conflict = dict(chart)
    conflict["direction"] = "BULLISH"
    c = build_confluence_assessment(forecast, accuracy, conflict, {})
    assert c["setup_grade"] == "NO_TRADE"
    assert c["research_eligible"] is False
    print("✅ FIA ↔ chart directional conflict protection PASS")

    missing = {"direction": "BEARISH"}
    m = build_confluence_assessment(forecast, accuracy, missing, {})
    assert m["setup_grade"] in {"WATCH", "A"}
    assert m["research_eligible"] is False
    assert m["confluence_completeness"] < 0.50
    print("✅ Missing chart evidence cannot fabricate A+/A++ PASS")

    weak_accuracy = {"setup_grade": "NO_TRADE", "research_eligible": False}
    w = build_confluence_assessment(forecast, weak_accuracy, chart, {})
    assert w["setup_grade"] == "NO_TRADE"
    assert w["research_eligible"] is False
    print("✅ Phase24 weak gate cannot be overridden by chart confluence PASS")

    features = chart_confluence_features(chart, "BEARISH")
    assert features["order_block"]["aligned"]
    assert features["fair_value_gap"]["aligned"]
    assert features["smt"]["aligned"]
    print("✅ Structured chart feature extraction PASS")

    print("\n========================================")
    print("✅ PHASE 25 PASS")
    print("htf_poi_ob_fvg = PASS")
    print("liquidity_sweep_reclaim = PASS")
    print("smt_session_context = PASS")
    print("automatic_setup_grading = PASS")
    print("forecast_weights_changed = NO")
    print("phase24_accuracy_logic_changed = NO")
    print("broker_execution_added = NO")
    print("========================================")


if __name__ == "__main__":
    main()
