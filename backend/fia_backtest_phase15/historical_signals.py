import yfinance as yf

TICKERS = {
    "nq": "NQ=F",
    "spx": "^GSPC",
    "dxy": "DX-Y.NYB",
    "us10y": "^TNX",
    "qqq": "QQQ",
    "nvda": "NVDA",
    "msft": "MSFT",
    "aapl": "AAPL",
    "amzn": "AMZN",
    "meta": "META",
    "avgo": "AVGO",
    "googl": "GOOGL",
    "amd": "AMD",
    "mu": "MU",
}

def historical_signals(timestamp):
    signals = {}

    for key, ticker in TICKERS.items():
        try:
            data = yf.Ticker(ticker).history(
                period="1y",
                interval="1h",
                auto_adjust=False,
            )

            if data is None or data.empty:
                signals[key] = None
                signals[f"{key}_prev"] = None
                continue

            data = data[data.index <= timestamp]

            if len(data) < 2:
                signals[key] = None
                signals[f"{key}_prev"] = None
                continue

            signals[key] = float(data["Close"].iloc[-1])
            signals[f"{key}_prev"] = float(data["Close"].iloc[-2])

        except Exception as exc:
            print(f"Historical {ticker} error: {exc}")
            signals[key] = None
            signals[f"{key}_prev"] = None

    return signals


if __name__ == "__main__":
    print("FIA Phase 15 Historical Signals: READY")
