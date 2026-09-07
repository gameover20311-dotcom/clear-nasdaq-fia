from fia_backtest_phase09.backtest.ablation import ablation_test


def main():
    sample_records = [
        {
            "signal": "trend",
            "horizon": "4H",
            "correct": True,
            "return_pct": 0.40,
        },
        {
            "signal": "liquidity",
            "horizon": "4H",
            "correct": True,
            "return_pct": 0.20,
        },
        {
            "signal": "trend",
            "horizon": "4H",
            "correct": False,
            "return_pct": -0.20,
        },
    ]

    result = ablation_test(sample_records, "trend")

    print(
        f"remove=trend | "
        f"baseline={result['baseline_observations']} | "
        f"ablated={result['ablated_observations']} | "
        f"baseline_accuracy={result['baseline_accuracy']} | "
        f"ablated_accuracy={result['ablated_accuracy']}"
    )


if __name__ == "__main__":
    main()
