from fia_backtest_phase08.backtest.attribution import attribute_signals


def main():
    sample_records = [
        {
            "signal": "trend",
            "horizon": "4H",
            "correct": True,
            "return_pct": 0.40,
            "signal_score": 0.80,
        },
        {
            "signal": "trend",
            "horizon": "4H",
            "correct": False,
            "return_pct": -0.20,
            "signal_score": 0.60,
        },
    ]

    result = attribute_signals(sample_records)

    for key, value in result.items():
        print(
            f"{key} -> "
            f"{value['observations']} observations, "
            f"accuracy={value['accuracy']}"
        )


if __name__ == "__main__":
    main()
