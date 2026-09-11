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


def run_case(name, overrides, expect_abstention=False):
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

    # NEUTRAL is still forbidden: the engine must never invent a third
    # directional label. NO_EDGE is not a direction, it is an abstention, and
    # it is only admissible where there is no evidence to take a side on.
    assert direction != "NEUTRAL"
    if expect_abstention:
        assert direction == "NO_EDGE", direction
        assert conf == 0.0, conf
    else:
        assert direction in ("BULLISH", "BEARISH"), direction
    assert abs((bull + bear) - 100.0) < 0.11
    assert 0.0 <= conf <= 100.0

    return forecast


def main():
    print("=== PHASE 21 LIVE ENGINE SMOKE TEST ===")

    # Every input is exactly 0.0, so there is no evidence for either side.
    # This case previously asserted ">=50.0 => BULLISH". That policy predates
    # the v665 abstention work and would now require the engine to publish a
    # direction it has no evidence for, which is the exact failure abstention
    # exists to prevent. Verified against the current engine: any non-zero
    # evidence still yields a direction (nq_structure=0.2 -> BULLISH), so the
    # directional path is intact and only this zero-evidence case abstains.
    balanced = run_case(
        "ZERO_EVIDENCE_ABSTENTION",
        {},
        expect_abstention=True,
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

    assert balanced.direction == "NO_EDGE", (
        "zero evidence must abstain, never publish a direction"
    )
    assert float(balanced.bullish_probability) == 50.0
    assert float(balanced.confidence) == 0.0

    assert bullish.direction == "BULLISH"
    assert bearish.direction == "BEARISH"

    # The directional path must not have been weakened by the abstention rule:
    # the smallest single piece of evidence still produces a direction.
    faint = run_case("FAINT_BULLISH_EVIDENCE", {"nq_structure": 0.2})
    assert faint.direction == "BULLISH"

    print()
    print("neutral_predictions_in_test = 0")
    print("abstentions_in_test = 1")
    print("probability_sum_check = PASS")
    print("confidence_range_check = PASS")
    print("zero_evidence_abstention = PASS")
    print("bullish_direction_check = PASS")
    print("bearish_direction_check = PASS")
    print("=== PHASE 21 LIVE ENGINE SMOKE TEST PASS ===")


if __name__ == "__main__":
    main()
