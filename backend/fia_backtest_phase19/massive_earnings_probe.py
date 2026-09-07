import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("POLYGON_API_KEY", "").strip()

TESTS = [
    ("NVDA", "2026-08-26"),
    ("INTC", "2026-07-24"),
    ("META", "2026-07-29"),
]


async def fetch(client, ticker, date):
    params = {
        "ticker": ticker,
        "date": date,
        "limit": 20,
        "sort": "date.asc",
        "apiKey": API_KEY,
    }

    response = await client.get(
        "https://api.massive.com/benzinga/v1/earnings",
        params=params,
    )

    return ticker, date, response


async def main():
    if not API_KEY:
        raise SystemExit("POLYGON_API_KEY is missing in .env")

    print("=== MASSIVE / BENZINGA EARNINGS ACCESS PROBE ===")

    async with httpx.AsyncClient(timeout=30) as client:
        for ticker, date in TESTS:
            ticker, date, response = await fetch(
                client,
                ticker,
                date,
            )

            print()
            print(ticker, date)
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

            for row in rows[:10]:
                print(
                    "  ticker =", row.get("ticker"),
                    "| date =", row.get("date"),
                    "| time =", row.get("time"),
                    "| date_status =", row.get("date_status"),
                    "| actual_eps =", row.get("actual_eps"),
                    "| estimated_eps =", row.get("estimated_eps"),
                    "| eps_surprise_percent =", row.get("eps_surprise_percent"),
                    "| actual_revenue =", row.get("actual_revenue"),
                    "| estimated_revenue =", row.get("estimated_revenue"),
                    "| fiscal =", row.get("fiscal_period"),
                    row.get("fiscal_year"),
                    "| last_updated =", row.get("last_updated"),
                )

    print()
    print("=== EARNINGS ACCESS PROBE COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
