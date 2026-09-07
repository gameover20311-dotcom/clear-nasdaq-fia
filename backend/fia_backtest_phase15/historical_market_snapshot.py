import asyncio
import yfinance as yf


TICKERS = {
    "nq": "NQ=F",
    "qqq": "QQQ",
    "dxy": "DX-Y.NYB",
    "us10y": "^TNX",
}


async def get_snapshot(timestamp):
    def load():
        result = {}
        for key, ticker in TICKERS.items():
            data = yf.Ticker(ticker).history(
                period="1y",
                interval="1h",
                auto_adjust=False,
            )
            result[key] = data
        return result

    data = await asyncio.to_thread(load)

    snapshot = {}

    for key, frame in data.items():
        if frame is None or frame.empty:
            snapshot[key] = None
            continue

        frame = frame[frame.index <= timestamp]

        snapshot[key] = (
            float(frame.iloc[-1]["Close"])
            if not frame.empty
            else None
        )

    return snapshot


if __name__ == "__main__":
    print("FIA Phase 15 Historical Market Snapshot: READY")
