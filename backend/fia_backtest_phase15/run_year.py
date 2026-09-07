import asyncio
from pathlib import Path

from .replay_runner import run_replay


async def main():
    root = Path(__file__).resolve().parents[1]

    csv_path = (
        root
        / "fia_backtest_phase14"
        / "data"
        / "historical_predictions.csv"
    )

    results = await run_replay(csv_path)

    print("FIA PHASE 15 REPLAY")
    print("records:", len(results))


if __name__ == "__main__":
    asyncio.run(main())
