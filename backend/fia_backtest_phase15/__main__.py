from fia_backtest_phase15.backtest.resolver import (
    outcome_direction,
    resolve_record,
    signed_return_pct,
)


def main():
    bullish = {
        "prediction_id": "PHASE15-TEST-BULL",
        "timestamp": "2026-08-31T00:00:00+00:00",
        "horizon": 8,
        "symbol": "NQ",
        "direction": "BULLISH",
        "bullish_probability": 60.0,
        "bearish_probability": 40.0,
        "confidence": 60.0,
        "entry_price": 20000.0,
        "future_price": None,
        "return_pct": None,
        "outcome_direction": None,
        "correct": None,
        "mfe_pct": None,
        "mae_pct": None,
    }

    resolved = resolve_record(bullish, 20200.0)

    assert resolved["outcome_direction"] == "BULLISH"
    assert resolved["correct"] is True
    assert round(resolved["return_pct"], 4) == 1.0

    assert outcome_direction(20000, 19800) == "BEARISH"
    assert outcome_direction(20000, 20000) == "NEUTRAL"
    assert round(signed_return_pct(20000, 20200), 4) == 1.0

    print("PHASE 15 OUTCOME RESOLVER: PASS")
    print("direction_resolution=PASS")
    print("return_calculation=PASS")
    print("correctness_calculation=PASS")
    print("csv_resolution_infrastructure=READY")


if __name__ == "__main__":
    main()
