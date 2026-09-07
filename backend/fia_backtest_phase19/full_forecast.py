import asyncio
import sys

from fia_backtest_phase19.full_snapshot import build_full_historical_snapshot
from fia_backtest_phase19.full_engine import build_forecast


async def main():
    ts = sys.argv[1] if len(sys.argv) > 1 else "2026-08-31T17:00:00+00:00"

    snapshot = await build_full_historical_snapshot(ts)
    forecast = build_forecast(snapshot)

    print("=== FIA PHASE 19 FULL FORECAST ===")
    print("timestamp =", snapshot.get("timestamp"))
    print("direction =", forecast.direction)
    print("bullish_probability =", forecast.bullish_probability)
    print("bearish_probability =", forecast.bearish_probability)
    print("confidence =", forecast.confidence)
    print("score =", forecast.score)
    print("regime =", forecast.regime)
    print("data_coverage =", forecast.data_coverage)
    print("intelligence_coverage =", forecast.intelligence_coverage)
    print()
    print("=== SIGNALS ===")
    for s in forecast.signals:
        print(
            s.name,
            "| score =", s.score,
            "| weight =", s.weight,
            "| freshness =", s.freshness,
        )
    print()
    print("=== SOURCE STATUS ===")
    for k, v in forecast.source_status.items():
        print(k, "=", v)
    print()
    print("=== THESIS ===")
    print(forecast.thesis)
    print()
    print("=== PHASE 19 FULL FORECAST COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
