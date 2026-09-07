from fia_backtest_phase11.backtest.validation import evaluate_holdout


def main():
    sample_records = [
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "correct": True,
            "return_pct": 0.20,
        },
        {
            "timestamp": "2026-01-02T00:00:00+00:00",
            "correct": False,
            "return_pct": -0.10,
        },
        {
            "timestamp": "2026-01-03T00:00:00+00:00",
            "correct": True,
            "return_pct": 0.30,
        },
        {
            "timestamp": "2026-01-04T00:00:00+00:00",
            "correct": True,
            "return_pct": 0.20,
        },
        {
            "timestamp": "2026-01-05T00:00:00+00:00",
            "correct": False,
            "return_pct": -0.20,
        },
    ]

    result = evaluate_holdout(sample_records, holdout_size=2)

    print(
        f"development={result['development_observations']} | "
        f"holdout={result['holdout_observations']} | "
        f"holdout_accuracy={result['holdout_accuracy']}"
    )


if __name__ == "__main__":
    main()
