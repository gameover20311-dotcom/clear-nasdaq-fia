import asyncio
from pathlib import Path
from .replay_runner import run_replay


async def main():
    root = Path(__file__).resolve().parents[1]
    path = root / "fia_backtest_phase14" / "data" / "historical_predictions.csv"

    results = await run_replay(path)

    total = len(results)
    bullish = sum(r["direction"] == "BULLISH" for r in results)
    bearish = sum(r["direction"] == "BEARISH" for r in results)
    neutral = sum(r["direction"] == "NEUTRAL" for r in results)

    print("=== FIA PHASE 15 REPORT ===")
    print("total_replayed:", total)
    print("bullish:", bullish)
    print("bearish:", bearish)
    print("neutral:", neutral)


if __name__ == "__main__":
    asyncio.run(main())
