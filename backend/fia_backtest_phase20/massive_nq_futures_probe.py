import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = (
    os.getenv("POLYGON_API_KEY")
    or os.getenv("MASSIVE_API_KEY")
    or ""
).strip()

BASE = "https://api.massive.com"

TEST_CONTRACTS = [
    ("NQU5", "2025-09-02", "2025-09-03"),
    ("NQZ5", "2025-10-01", "2025-10-02"),
    ("NQH6", "2026-02-02", "2026-02-03"),
    ("NQM6", "2026-05-04", "2026-05-05"),
    ("NQU6", "2026-08-03", "2026-08-04"),
]


async def main():
    if not API_KEY:
        raise SystemExit(
            "POLYGON_API_KEY / MASSIVE_API_KEY missing in .env"
        )

    print("=== PHASE 20 MASSIVE NQ FUTURES ACCESS PROBE ===")
    print()

    async with httpx.AsyncClient(timeout=30) as client:

        # Reference-contract discovery probe.
        response = await client.get(
            f"{BASE}/futures/v1/contracts",
            params={
                "product_code": "NQ",
                "limit": 10,
                "apiKey": API_KEY,
            },
        )

        print("CONTRACTS ENDPOINT")
        print("http_status =", response.status_code)

        if response.status_code == 200:
            payload = response.json()
            results = payload.get("results") or []
            print("count =", len(results))

            for row in results[:10]:
                print(
                    " ",
                    row.get("ticker"),
                    "| first_trade_date =",
                    row.get("first_trade_date"),
                    "| last_trade_date =",
                    row.get("last_trade_date"),
                    "| active =",
                    row.get("active"),
                )
        else:
            try:
                payload = response.json()
                message = (
                    payload.get("error")
                    or payload.get("message")
                    or payload.get("status")
                )
            except Exception:
                message = response.text[:300]

            print("message =", message)

        print()
        print("5-MINUTE AGGREGATE TESTS")

        for ticker, start, end in TEST_CONTRACTS:
            response = await client.get(
                f"{BASE}/futures/v1/aggs/{ticker}",
                params={
                    "resolution": "5min",
                    "window_start.gte": start,
                    "window_start.lt": end,
                    "limit": 5000,
                    "apiKey": API_KEY,
                },
            )

            print()
            print(ticker, start, "->", end)
            print("http_status =", response.status_code)

            if response.status_code != 200:
                try:
                    payload = response.json()
                    message = (
                        payload.get("error")
                        or payload.get("message")
                        or payload.get("status")
                    )
                except Exception:
                    message = response.text[:300]

                print("message =", message)
                continue

            payload = response.json()
            rows = payload.get("results") or []

            print("api_status =", payload.get("status"))
            print("count =", len(rows))

            if rows:
                first = rows[0]
                last = rows[-1]

                print(
                    "first_window_start =",
                    first.get("window_start"),
                    "| ohlcv =",
                    first.get("open"),
                    first.get("high"),
                    first.get("low"),
                    first.get("close"),
                    first.get("volume"),
                )

                print(
                    "last_window_start =",
                    last.get("window_start"),
                    "| ohlcv =",
                    last.get("open"),
                    last.get("high"),
                    last.get("low"),
                    last.get("close"),
                    last.get("volume"),
                )

    print()
    print("=== NQ FUTURES ACCESS PROBE COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
