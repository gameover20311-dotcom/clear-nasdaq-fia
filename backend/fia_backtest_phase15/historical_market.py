from datetime import datetime, timezone
import asyncio
import yfinance as yf


def normalize_timestamp(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(
            float(value),
            tz=timezone.utc,
        )

    value = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


async def get_historical_nq_price(target_timestamp):
    target = normalize_timestamp(target_timestamp)

    def load_data():
        return yf.Ticker("NQ=F").history(
            period="1y",
            interval="1h",
            auto_adjust=False,
        )

    try:
        data = await asyncio.to_thread(load_data)
    except Exception as exc:
        print(f"Historical NQ data error: {exc}")
        return None

    if data is None or data.empty:
        return None

    if data.index.tz is None:
        data.index = data.index.tz_localize(timezone.utc)
    else:
        data.index = data.index.tz_convert(timezone.utc)

    eligible = data[data.index <= target]

    if eligible.empty:
        return None

    return float(eligible.iloc[-1]["Close"])


if __name__ == "__main__":
    print("FIA Phase 15 Historical Market Loader: READY")
