from fia.engine import build_forecast


BASE = {
    "nq_structure": 0.0,
    "spx_confirmation": 0.0,
    "dxy": 0.0,
    "us10y": 0.0,
    "mega_cap": 0.0,
    "semis": 0.0,
    "breadth": 0.0,
    "liquidity_signal": 0.0,
    "news": 0.0,
    "macro": 0.0,
    "earnings": 0.0,
    "provider_candle_evidence": "available",
}


def run_case(name, overrides):
    data = dict(BASE)
    data.update(overrides)

    forecast = build_forecast(
        {
            "status": "SMOKE_TEST",
            "timestamp": "2026-09-01T00:00:00+00:00",
            "data": data,
        }
    )

    bull = float(forecast.bullish_probability)
    bear = float(forecast.bearish_probability)
    conf = float(forecast.confidence)
    direction = str(forecast.direction)

    print(
        name,
        "| direction =", direction,
        "| bull =", bull,
        "| bear =", bear,
        "| confidence =", conf,
    )

    assert direction in ("BULLISH", "BEARISH")
    assert direction != "NEUTRAL"
    assert abs((bull + bear) - 100.0) < 0.11
    assert 0.0 <= conf <= 100.0

    return forecast


def main():
    print("=== PHASE 21 LIVE ENGINE SMOKE TEST ===")

    balanced = run_case(
        "BALANCED_50_BOUNDARY",
        {},
    )

    bullish = run_case(
        "BULLISH_EVIDENCE",
        {
            "nq_structure": 0.45,
            "spx_confirmation": 0.30,
            "mega_cap": 0.40,
            "semis": 0.35,
            "breadth": 0.20,
            "liquidity_signal": 1.0,
            "news": 0.25,
        },
    )

    bearish = run_case(
        "BEARISH_EVIDENCE",
        {
            "nq_structure": -0.45,
            "spx_confirmation": -0.30,
            "mega_cap": -0.40,
            "semis": -0.35,
            "breadth": -0.20,
            "liquidity_signal": -1.0,
            "news": -0.25,
        },
    )

    assert (
        balanced.direction == "BULLISH"
    ), (
        "50.0 boundary should follow the validated "
        "Phase 21 policy: >=50.0 => BULLISH"
    )

    assert bullish.direction == "BULLISH"
    assert bearish.direction == "BEARISH"

    print()
    print("neutral_predictions_in_test = 0")
    print("probability_sum_check = PASS")
    print("confidence_range_check = PASS")
    print("50.0_boundary_policy = PASS")
    print("bullish_direction_check = PASS")
    print("bearish_direction_check = PASS")
    print("=== PHASE 21 LIVE ENGINE SMOKE TEST PASS ===")


if __name__ == "__main__":
    main()
