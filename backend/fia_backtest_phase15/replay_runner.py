from pathlib import Path

from fia.engine import build_forecast

from .historical_loader import load_historical_predictions
from .snapshot_builder import build_historical_snapshot


async def run_replay(csv_path):
    rows = load_historical_predictions(csv_path)
    results = []

    for row in rows:
        timestamp = row.get("timestamp")
        if not timestamp:
            continue

        snapshot = await build_historical_snapshot(
            timestamp=timestamp,
            raw_data=row,
        )

        forecast = build_forecast(snapshot)

        results.append({
            "timestamp": timestamp,
            "direction": forecast.direction,
            "bullish_probability": forecast.bullish_probability,
            "bearish_probability": forecast.bearish_probability,
            "confidence": forecast.confidence,
        })

    return results


if __name__ == "__main__":
    print("FIA Phase 15 Replay Runner: READY")
