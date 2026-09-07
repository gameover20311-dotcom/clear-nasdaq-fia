from fia_backtest_phase10.backtest.walk_forward import (
    build_walk_forward_windows,
    summarize_walk_forward,
)


def main():
    sample_records = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "correct": True, "return_pct": 0.2},
        {"timestamp": "2026-01-02T00:00:00+00:00", "correct": False, "return_pct": -0.1},
        {"timestamp": "2026-01-03T00:00:00+00:00", "correct": True, "return_pct": 0.3},
        {"timestamp": "2026-01-04T00:00:00+00:00", "correct": True, "return_pct": 0.2},
        {"timestamp": "2026-01-05T00:00:00+00:00", "correct": False, "return_pct": -0.2},
        {"timestamp": "2026-01-06T00:00:00+00:00", "correct": True, "return_pct": 0.4},
    ]

    windows = build_walk_forward_windows(
        sample_records,
        train_size=3,
        validation_size=2,
        step_size=1,
    )

    summary = summarize_walk_forward(windows)

    print(
        f"windows={summary['windows']} | "
        f"avg_validation_accuracy="
        f"{summary['average_validation_accuracy']}"
    )


if __name__ == "__main__":
    main()
