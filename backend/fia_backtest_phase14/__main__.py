from pathlib import Path

from fia_backtest_phase14.backtest.recorder import (
    build_prediction_record,
    append_prediction,
)


def main():
    root = Path.cwd()

    forecast = {
        "symbol": "NQ",
        "horizon_hours": 4,
        "direction": "BULLISH",
        "bullish_probability": 64.0,
        "bearish_probability": 36.0,
        "confidence": 70.0,
    }

    record = build_prediction_record(
        forecast,
        entry_price=20000.0,
        timestamp="2026-08-31T15:00:00+00:00",
    )

    output = (
        root
        / "fia_backtest_phase14"
        / "data"
        / "historical_predictions.csv"
    )

    print("Recorder schema OK")
    print(f"prediction_id={record['prediction_id']}")
    print(f"symbol={record['symbol']}")
    print(f"horizon={record['horizon']}")
    print(f"direction={record['direction']}")
    print(f"entry_price={record['entry_price']}")

    # Test only: do not write the sample record into the real dataset.
    print(f"real_dataset_path={output}")
    print("sample_write=SKIPPED")


if __name__ == "__main__":
    main()
