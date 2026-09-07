# PHASE22_TRUTH_CONSISTENCY_V1
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fia.engine import build_forecast, _impact_coverage
from fia.intelligence import intelligent_score, intelligence_coverage
from fia.liquidity import build_liquidity_groups
from fia.models import Signal


def assert_true(name, condition, detail=""):
    if not condition:
        raise AssertionError(f"{name} FAIL {detail}")
    print(f"✅ {name}")


def base_data():
    return {
        "provider_quotes_available": 17,
        "provider_candle_evidence": "available",
        "nq_structure": -0.55,
        "spx_confirmation": -0.40,
        "dxy": 0.10,
        "us10y": -0.30,
        "mega_cap": -0.45,
        "semis": -0.60,
        "breadth": -0.35,
        "news": -0.20,
        "news_articles": 12,
        "news_scored_articles": 5,
        "news_status": "live_scored",
        "macro": 0.0,
        "earnings": 0.0,
        "price": 710.0,
        "nq_futures_price": 29300.0,
        "monthly_high": 735.0,
        "monthly_low": 685.0,
        "weekly_high": 720.0,
        "weekly_low": 700.0,
        "daily_high": 715.0,
        "daily_low": 705.0,
        "asia_high": 29420.0,
        "asia_low": 29120.0,
        "london_high": 29380.0,
        "london_low": 29080.0,
        "new_york_high": 29510.0,
        "new_york_low": 29220.0,
        "qqq_liquidity": {
            "current_price": 710.0,
            "source": "TEST_QQQ_REFERENCE",
            "levels": {
                "monthly_high": 735.0, "monthly_low": 685.0,
                "weekly_high": 720.0, "weekly_low": 700.0,
                "daily_high": 715.0, "daily_low": 705.0,
            },
        },
        "nq_liquidity": {
            "current_price": 29300.0,
            "source": "TEST_EXPLICIT_NQ",
            "levels": {
                "monthly_high": 29600.0, "monthly_low": 28600.0,
                "weekly_high": 29550.0, "weekly_low": 28950.0,
                "daily_high": 29480.0, "daily_low": 29050.0,
                "asia_high": 29420.0, "asia_low": 29120.0,
                "london_high": 29380.0, "london_low": 29080.0,
                "new_york_high": 29510.0, "new_york_low": 29220.0,
            },
        },
    }


def main():
    data = base_data()
    fc = build_forecast({"data": data})

    assert_true("direction is binary", fc.direction in {"BULLISH", "BEARISH"})
    assert_true("thesis matches direction", fc.direction.lower() in fc.thesis.lower(), fc.thesis)
    assert_true("probabilities sum 100", abs(fc.bullish_probability + fc.bearish_probability - 100.0) < 0.11)
    assert_true("truth validator PASS", bool(fc.consistency.get("pass")), str(fc.consistency))

    expected_weights = {
        "NQ structure": 0.20, "SPX confirmation": 0.10, "DXY": 0.08,
        "US10Y": 0.07, "Mega-cap leadership": 0.20, "Semiconductors": 0.12,
        "Breadth": 0.08, "News": 0.07, "Macro calendar": 0.04,
        "Earnings/guidance": 0.04,
    }
    actual_weights = {s.name: round(float(s.weight), 2) for s in fc.signals}
    assert_true("Phase21 weights unchanged", actual_weights == expected_weights, str(actual_weights))

    # Missing evidence must not dilute the intelligence score like a neutral vote.
    active = [
        Signal(name="NQ structure", score=-0.5, weight=0.2, detail="live", freshness="live"),
        Signal(name="Mega-cap leadership", score=-0.4, weight=0.2, detail="live", freshness="live"),
    ]
    with_missing = active + [
        Signal(name="US10Y", score=0.0, weight=0.07, detail="Awaiting provider data", freshness="missing"),
    ]
    score_active, _ = intelligent_score(active)
    score_missing, _ = intelligent_score(with_missing)
    assert_true("missing != neutral vote", abs(score_active - score_missing) < 1e-12, f"{score_active} vs {score_missing}")
    assert_true("missing lowers coverage", intelligence_coverage(with_missing) < intelligence_coverage(active))

    # News truth: no scorable articles => missing signal, not neutral market opinion.
    no_news = base_data()
    no_news.update({"news": None, "news_articles": 20, "news_scored_articles": 0, "news_status": "live_unscored"})
    fc2 = build_forecast({"data": no_news})
    news_signal = next(s for s in fc2.signals if s.name == "News")
    assert_true("unscored news marked missing", news_signal.freshness == "missing")
    assert_true("news source status truthful", "unscored" in fc2.source_status.get("news", ""))

    missing_macro = base_data()
    missing_macro.update({"macro": None, "macro_status": "missing"})
    fc3 = build_forecast({"data": missing_macro})
    macro_signal = next(s for s in fc3.signals if s.name == "Macro calendar")
    assert_true("missing macro not neutral", macro_signal.freshness == "missing")

    # All expected inputs live => data coverage exactly 1.0.
    assert_true("data coverage definition", abs(fc.data_coverage - 1.0) < 1e-9, str(fc.data_coverage))
    assert_true("intelligence coverage range", 0.0 < fc.intelligence_coverage <= 1.0)

    # Liquidity must use QQQ price for QQQ levels, NQ price for NQ levels.
    groups = build_liquidity_groups(data)
    assert_true("QQQ group tagged", groups["qqq"]["instrument"] == "QQQ")
    assert_true("NQ group tagged", groups["nq"]["instrument"] == "NQ")
    qdist = groups["qqq"]["levels"]["daily_high"].distance_pct
    ndist = groups["nq"]["levels"]["asia_high"].distance_pct
    assert_true("QQQ distance sane", qdist is not None and qdist < 10.0, str(qdist))
    assert_true("NQ distance sane", ndist is not None and ndist < 10.0, str(ndist))

    print()
    print("========================================")
    print("✅ PHASE 22 PASS")
    print("truth_consistency = PASS")
    print("news_consistency = PASS")
    print("liquidity_separation = PASS")
    print("missing_data_semantics = PASS")
    print("forecast_weights_changed = NO")
    print("broker_execution_added = NO")
    print("========================================")


if __name__ == "__main__":
    main()
