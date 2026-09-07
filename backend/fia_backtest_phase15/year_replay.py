from pathlib import Path

from .historical_loader import load_historical_predictions
from .replay_runner import run_one_replay


def run_historical_replay(csv_path):
    rows = load_historical_predictions(csv_path)

    results = []

    for row in rows:
        timestamp = row.get("timestamp")
        if not timestamp:
            continue

        raw_data = {}

        forecast = run_one_replay(
            raw_data=raw_data,
            timestamp=timestamp,
        )

        results.append({
            "timestamp": timestamp,
            "direction": forecast.direction,
            "bullish_probability": forecast.bullish_probability,
            "bearish_probability": forecast.bearish_probability,
            "confidence": forecast.confidence,
        })

    return results


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]

    csv_path = (
        root
        / "fia_backtest_phase14"
        / "data"
        / "historical_predictions.csv"
    )

    results = run_historical_replay(csv_path)

    print("FIA PHASE 15 HISTORICAL REPLAY")
    print(f"replayed_predictions={len(results)}")
