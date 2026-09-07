from .attribution import attribute_signals


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
        print(key, "->", value["observations"], "observations")


if __name__ == "__main__":
    main()
