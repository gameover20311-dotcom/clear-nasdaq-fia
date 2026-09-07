#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fia_backtest_phase28.historical_chart import build_historical_chart_analysis
from fia_backtest_phase28.phase28_data import ES_CACHE, NQ_CACHE, FuturesCache
from fia_backtest_phase28.truth_metrics import (
    futures_outcome_scheduled,
    metric,
    resolved_bool,
)


def check(name, condition, detail=""):
    if not condition:
        raise AssertionError("{} FAIL {}".format(name, detail))
    print("PASS", name)


def main():
    check("boolean False is resolved", resolved_bool(False) is False)
    sample = [
        {"correct_4h": True, "actual_4h": "BULLISH", "bullish_probability": 60},
        {"correct_4h": False, "actual_4h": "BEARISH", "bullish_probability": 60},
    ]
    sample_metric = metric(sample, 4)
    check("loss stays in denominator", sample_metric["n"] == 2, sample_metric)
    check("metric is 50 percent", sample_metric["accuracy"] == 50.0, sample_metric)
    friday = datetime(2026, 6, 5, 17, 0, tzinfo=timezone.utc)
    check("Friday +8H closure is not expected", not futures_outcome_scheduled(friday, 8))
    check("Friday +4H bar is expected", futures_outcome_scheduled(friday, 4))

    legacy_csv = ROOT / "fia_backtest_phase28" / "results" / "phase28_market_grade_replay_1y.csv"
    with legacy_csv.open(newline="", encoding="utf-8") as handle:
        legacy_rows = list(csv.DictReader(handle))
    four = metric(legacy_rows, 4)
    eight = metric(legacy_rows, 8)
    check("legacy 4H fake-perfect claim detected", four["n"] == 249 and four["correct"] == 115, four)
    check("legacy 8H fake-perfect claim detected", eight["n"] == 200 and eight["correct"] == 91, eight)

    nq = FuturesCache(NQ_CACHE)
    es = FuturesCache(ES_CACHE)
    check("Massive NQ cache available", nq.available and nq.bar_count > 80000, nq.bar_count)
    target = datetime(2026, 6, 3, 17, 0, tzinfo=timezone.utc)
    contract, entry, _ = nq.last_completed(target)
    out4, _ = nq.last_completed_for_contract(contract, target.replace(hour=21))
    check("entry-time contract freezes outcome", entry is not None and out4 is not None)
    check("entry is completed PTI bar", entry["timestamp"].hour <= 16)

    bullish_chart = build_historical_chart_analysis(target, "BULLISH", nq, es)
    bearish_chart = build_historical_chart_analysis(target, "BEARISH", nq, es)
    check("chart extraction ignores forecast direction", bullish_chart == bearish_chart)
    check("chart independence is explicit", bullish_chart.get("forecast_direction_used_for_detection") is False)

    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    check("yfinance dependency declared once", requirements.count("yfinance") == 1)
    check("google-genai dependency declared once", requirements.count("google-genai") == 1)
    print("PHASE 29 TRUTH TEST PASS")


if __name__ == "__main__":
    main()
