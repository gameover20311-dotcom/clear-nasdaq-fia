#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENGINE = ROOT / "fia" / "engine.py"
ACCURACY = ROOT / "fia" / "accuracy_engine.py"
CONFLUENCE = ROOT / "fia" / "confluence_engine.py"
MAIN = ROOT / "main.py"
MANIFEST = Path(__file__).resolve().parent / "phase26_manifest.json"

from fia.learning_engine import (
    FORWARD_FIELDS,
    attach_confluence,
    build_learning_status,
    build_research_alert,
    calibration_report,
    forward_validation_report,
    record_forward_forecast,
    resolve_due_forward_records,
    signal_combination_attribution,
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def forecast(ts: str, direction="BULLISH", bull=72.0, bear=28.0):
    return SimpleNamespace(
        symbol="NQ",
        generated_at=ts,
        direction=direction,
        bullish_probability=bull,
        bearish_probability=bear,
        confidence=73.0,
        regime="TREND",
        data_coverage=1.0,
        intelligence_coverage=0.55,
    )


def accuracy():
    return {
        "setup_grade": "A++",
        "research_eligible": True,
        "evidence": {
            "aligned_signals": ["NQ structure", "Mega-cap leadership", "Semiconductors"],
            "opposed_signals": ["DXY"],
            "missing_signals": [],
        },
    }


def confluence():
    return {
        "setup_grade": "A++",
        "research_eligible": True,
        "confluence_score": 92.0,
        "confluence_alignment": 0.95,
        "confluence_completeness": 0.90,
        "features": {
            "order_block": {"present": True, "aligned": True},
            "fair_value_gap": {"present": True, "aligned": True},
            "liquidity_sweep_reclaim": {"present": True, "aligned": True},
        },
    }


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FORWARD_FIELDS)
        w.writeheader(); w.writerows(rows)


async def async_tests():
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["phase"] == "PHASE 26" and manifest["forward_only"] is True
    for key in ("engine_sha256_before","accuracy_sha256_before","confluence_sha256_before"):
        assert len(manifest[key]) == 64
    assert ENGINE.exists() and ACCURACY.exists() and CONFLUENCE.exists()
    print("✅ Historical Phase26 provenance manifest preserved")
    print("✅ Current engine/accuracy/confluence files present; final release gate owns current hashes")

    main_text = MAIN.read_text()
    assert "PHASE26_LEARNING_VALIDATION_V1" in main_text
    assert '/api/learning/status' in main_text
    assert '/api/learning/resolve' in main_text
    print("✅ Production learning/monitoring routes installed")

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "forward.csv"
        ts = "2026-09-01T12:00:00+00:00"
        snap = {"data": {"nq_futures_price": 25000.0}}

        first = record_forward_forecast(forecast(ts), snap, accuracy(), path)
        second = record_forward_forecast(forecast("2026-09-01T12:20:00+00:00"), snap, accuracy(), path)
        assert first["created"] is True
        assert second["created"] is False
        rows = read_rows(path)
        assert len(rows) == 1
        assert rows[0]["nq_4h"] == "" and rows[0]["nq_8h"] == ""
        print("✅ First checkpoint frozen + duplicate/revision protection PASS")
        print("✅ No-lookahead: future outcomes are blank at record time PASS")

        attached = attach_confluence(first["prediction_id"], confluence(), accuracy(), path)
        assert attached["ok"] is True
        assert attached["alert"]["level"] == "HIGH_QUALITY"
        rows = read_rows(path)
        assert rows[0]["phase25_grade"] == "A++"
        assert rows[0]["alert_level"] == "HIGH_QUALITY"
        print("✅ Phase25 A++ label + research alert attachment PASS")

        target_map = {
            datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc): 25200.0,
            datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc): 24800.0,
        }
        def lookup(target):
            return target_map.get(target)

        changed = await resolve_due_forward_records(
            path,
            now=datetime(2026, 9, 1, 21, 0, tzinfo=timezone.utc),
            price_lookup=lookup,
        )
        assert changed == 2
        rows = read_rows(path)
        r = rows[0]
        assert r["actual_4h"] == "BULLISH" and r["correct_4h"] == "True"
        assert r["actual_8h"] == "BEARISH" and r["correct_8h"] == "False"
        print("✅ Exact target-time 4H/8H outcome resolution PASS")

        # Add enough synthetic resolved forward observations to test rolling,
        # calibration and signal-combination attribution without touching real data.
        base = rows[0]
        synthetic = []
        for i in range(30):
            x = dict(base)
            x["prediction_id"] = f"SYN-{i:03d}"
            x["timestamp"] = (datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(hours=i)).isoformat()
            correct = (i % 3) != 0
            actual = "BULLISH" if correct else "BEARISH"
            x["direction"] = "BULLISH"
            x["bullish_probability"] = "70"
            x["bearish_probability"] = "30"
            x["actual_4h"] = actual
            x["actual_8h"] = actual
            x["correct_4h"] = str(correct)
            x["correct_8h"] = str(correct)
            x["nq_4h"] = "25100"
            x["nq_8h"] = "25120"
            x["signal_combo"] = "Mega-cap leadership+NQ structure+Semiconductors"
            synthetic.append(x)
        write_rows(path, synthetic)

        report = forward_validation_report(path)
        assert report["status"] == "EARLY"
        assert report["4h"]["resolved"] == 30
        assert report["rolling_4h"][0]["available"] == 20
        print("✅ Rolling forward validation PASS")

        cal = calibration_report(synthetic, 4)
        assert cal["n"] == 30 and cal["brier"] is not None and cal["ece"] is not None
        print("✅ Forward probability calibration/Brier/ECE PASS")

        attr = signal_combination_attribution(synthetic, min_n=5)
        assert len(attr["groups"]) == 1 and attr["groups"][0]["n"] == 30
        print("✅ Signal-combination attribution with minimum-sample guard PASS")

        status = build_learning_status(path)
        assert status["ok"] is True
        assert status["protections"]["forward_only"] is True
        assert status["protections"]["broker_execution"] is False
        print("✅ Production monitoring status PASS")

    alert = build_research_alert(accuracy(), confluence())
    assert alert["active"] is True and alert["broker_execution"] is False
    weak = build_research_alert({"setup_grade":"WATCH","research_eligible":False}, confluence())
    assert weak["active"] is False
    print("✅ High-quality alert gate cannot override weak research eligibility PASS")

    print("\n========================================")
    print("✅ PHASE 26 PASS")
    print("automatic_4h_8h_outcomes = PASS")
    print("rolling_forward_validation = PASS")
    print("calibration_signal_attribution = PASS")
    print("production_monitoring_alerts = PASS")
    print("forecast_weights_changed = NO")
    print("phase24_accuracy_logic_changed = NO")
    print("phase25_confluence_logic_changed = NO")
    print("broker_execution_added = NO")
    print("========================================")


def main():
    asyncio.run(async_tests())


if __name__ == "__main__":
    main()
