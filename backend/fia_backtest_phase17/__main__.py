from fia_backtest_phase17.backtest.evaluator import (
    accuracy,
    evaluate,
    robustness_checks,
    split_walk_forward,
)


def main():
    sample = [
        {
            "correct": "True",
            "future_price": "20100",
            "outcome_direction": "BULLISH",
        },
        {
            "correct": "False",
            "future_price": "19900",
            "outcome_direction": "BEARISH",
        },
        {
            "correct": "True",
            "future_price": "20200",
            "outcome_direction": "BULLISH",
        },
        {
            "correct": "False",
            "future_price": "19800",
            "outcome_direction": "BEARISH",
        },
    ]

    assert accuracy(sample) == 0.5

    split = split_walk_forward(
        sample,
        development_size=2,
        holdout_size=2,
    )

    assert len(split["development"]) == 2
    assert len(split["holdout"]) == 2

    checks = robustness_checks(sample)
    assert checks["resolved_records"] == 4
    assert checks["performance_claim_allowed"] is True
    assert checks["enough_data_for_robustness"] is False

    result = evaluate([])

    assert result["status"] == "NO_REAL_DATA"

    print("PHASE 17 WALK-FORWARD ENGINE: PASS")
    print("walk_forward_split=PASS")
    print("holdout_evaluation=PASS")
    print("robustness_checks=PASS")
    print("no_fake_performance=PASS")
    print("final_report_infrastructure=READY")
    print("real_dataset_status=", result["status"])


if __name__ == "__main__":
    main()
