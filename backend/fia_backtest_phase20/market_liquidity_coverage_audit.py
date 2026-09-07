from datetime import datetime, timezone
import yfinance as yf

START = datetime(2025, 9, 1, tzinfo=timezone.utc)
END = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)

TICKERS_1H = [
    "NQ=F", "QQQ", "SPY", "DX-Y.NYB", "^TNX",
    "NVDA", "MSFT", "AAPL", "AMZN", "META",
    "AVGO", "GOOGL", "GOOG", "TSLA", "NFLX",
    "AMD", "MU", "INTC", "QCOM", "SMCI",
]


def fmt_index(df):
    if df is None or df.empty:
        return None, None, 0

    idx = df.index

    try:
        first = idx[0].isoformat()
        last = idx[-1].isoformat()
    except Exception:
        first = str(idx[0])
        last = str(idx[-1])

    return first, last, len(df)


print("=== PHASE 20 MARKET / LIQUIDITY COVERAGE AUDIT ===")
print("required window =", START.isoformat(), "->", END.isoformat())
print()

print("=== 1H MARKET DATA ===")

one_hour_ok = 0
one_hour_missing = []

for ticker in TICKERS_1H:
    try:
        df = yf.Ticker(ticker).history(
            period="2y",
            interval="1h",
            auto_adjust=False,
            prepost=False,
        )
        first, last, rows = fmt_index(df)

        covers_start = False

        if df is not None and not df.empty:
            first_dt = df.index[0]

            if first_dt.tzinfo is None:
                first_dt = first_dt.tz_localize("UTC")
            else:
                first_dt = first_dt.tz_convert("UTC")

            covers_start = (
                first_dt.to_pydatetime()
                <= START
            )

        print(
            ticker,
            "| rows =", rows,
            "| first =", first,
            "| last =", last,
            "| covers_2025_09_01 =", covers_start,
        )

        if covers_start:
            one_hour_ok += 1
        else:
            one_hour_missing.append(ticker)

    except Exception as exc:
        print(
            ticker,
            "| ERROR =",
            repr(exc),
        )
        one_hour_missing.append(ticker)

print()
print("=== NQ 5M LIQUIDITY DATA ===")

try:
    nq5 = yf.Ticker("NQ=F").history(
        period="60d",
        interval="5m",
        auto_adjust=False,
        prepost=True,
    )

    first5, last5, rows5 = fmt_index(nq5)

    print("rows =", rows5)
    print("first =", first5)
    print("last =", last5)

    covers_one_year = False

    if nq5 is not None and not nq5.empty:
        first_dt = nq5.index[0]

        if first_dt.tzinfo is None:
            first_dt = first_dt.tz_localize("UTC")
        else:
            first_dt = first_dt.tz_convert("UTC")

        covers_one_year = (
            first_dt.to_pydatetime()
            <= START
        )

    print(
        "covers_full_phase20_window =",
        covers_one_year,
    )

except Exception as exc:
    rows5 = 0
    first5 = None
    last5 = None
    covers_one_year = False

    print("ERROR =", repr(exc))

print()
print("=== COVERAGE SUMMARY ===")
print(
    "1H tickers covering full window =",
    one_hour_ok,
    "/",
    len(TICKERS_1H),
)
print(
    "1H missing/short tickers =",
    one_hour_missing,
)
print(
    "NQ 5M covers full window =",
    covers_one_year,
)
print(
    "NQ 5M first =",
    first5,
)
print(
    "NQ 5M last =",
    last5,
)

if one_hour_ok == len(TICKERS_1H) and covers_one_year:
    verdict = "READY_FOR_FULL_PARITY_BACKTEST"
elif one_hour_ok == len(TICKERS_1H):
    verdict = "MARKET_READY_BUT_5M_LIQUIDITY_HISTORY_MISSING"
else:
    verdict = "MARKET_AND_OR_LIQUIDITY_HISTORY_INCOMPLETE"

print("verdict =", verdict)
print(
    "=== PHASE 20 MARKET / LIQUIDITY COVERAGE AUDIT COMPLETE ==="
)
