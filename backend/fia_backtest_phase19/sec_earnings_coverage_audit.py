import asyncio
import os
from collections import defaultdict

import httpx
from dotenv import load_dotenv

load_dotenv()

START = "2026-07-01"
END = "2026-08-31"

# Direct SEC CIK map for the 15 tracked FIA companies.
# GOOG and GOOGL share Alphabet's CIK.
COMPANIES = {
    "NVDA": 1045810,
    "MSFT": 789019,
    "AAPL": 320193,
    "AMZN": 1018724,
    "META": 1326801,
    "AVGO": 1730168,
    "GOOGL": 1652044,
    "GOOG": 1652044,
    "TSLA": 1318605,
    "NFLX": 1065280,
    "AMD": 2488,
    "MU": 723125,
    "INTC": 50863,
    "QCOM": 804328,
    "SMCI": 1375365,
}

# SEC recommends a declared User-Agent with organization + contact email.
# If SEC_USER_AGENT is present in .env, it will be used.
USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "CLEAR-NASDAQ-FIA historical-backtest",
).strip()

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json,text/plain,*/*",
}


def safe_get(values, index, default=None):
    try:
        return values[index]
    except Exception:
        return default


def parse_recent_filings(payload):
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    rows = []

    for i in range(len(forms)):
        rows.append({
            "form": safe_get(forms, i),
            "filingDate": safe_get(recent.get("filingDate", []), i),
            "reportDate": safe_get(recent.get("reportDate", []), i),
            "acceptanceDateTime": safe_get(
                recent.get("acceptanceDateTime", []), i
            ),
            "accessionNumber": safe_get(
                recent.get("accessionNumber", []), i
            ),
            "primaryDocument": safe_get(
                recent.get("primaryDocument", []), i
            ),
            "primaryDocDescription": safe_get(
                recent.get("primaryDocDescription", []), i
            ),
            "items": safe_get(recent.get("items", []), i, ""),
        })

    return rows


def in_range(day):
    return bool(day and START <= day <= END)


def is_earnings_8k(row):
    if row.get("form") not in ("8-K", "8-K/A"):
        return False

    items = str(row.get("items") or "")
    if "2.02" in items:
        return True

    desc = str(row.get("primaryDocDescription") or "").lower()
    return any(
        phrase in desc
        for phrase in (
            "earnings",
            "financial results",
            "results of operations",
        )
    )


async def fetch_submission(client, cik):
    cik10 = str(cik).zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik10}.json"

    last_status = None
    last_text = ""

    for attempt in range(1, 5):
        response = await client.get(
            url,
            headers=HEADERS,
            timeout=30,
        )

        last_status = response.status_code
        last_text = response.text[:300]

        if response.status_code == 200:
            return response.json()

        if response.status_code in (403, 429):
            await asyncio.sleep(2.0 * attempt)
            continue

        break

    raise RuntimeError(
        f"SEC HTTP {last_status} for CIK {cik10}: {last_text}"
    )


async def main():
    print("=== PHASE 19 SEC EARNINGS COVERAGE AUDIT V2 ===")
    print("window =", START, "->", END)
    print("SEC user-agent =", USER_AGENT)
    print("ticker-map dependency = DISABLED")
    print()

    # Deduplicate Alphabet CIK while preserving both tracked tickers.
    cik_to_symbols = defaultdict(list)
    for symbol, cik in COMPANIES.items():
        cik_to_symbols[cik].append(symbol)

    events = []
    failed = []

    async with httpx.AsyncClient(
        follow_redirects=True,
        http2=False,
    ) as client:

        for cik, symbols in cik_to_symbols.items():
            label = "/".join(symbols)

            try:
                payload = await fetch_submission(client, cik)
            except Exception as exc:
                print(label, "| ERROR =", repr(exc))
                failed.extend(symbols)
                await asyncio.sleep(0.5)
                continue

            company_name = payload.get("name")
            rows = parse_recent_filings(payload)

            candidates = [
                row
                for row in rows
                if in_range(row.get("filingDate"))
                and is_earnings_8k(row)
            ]

            print(
                label,
                "|", company_name,
                "| CIK =", str(cik).zfill(10),
                "| Item2.02 candidates =", len(candidates),
            )

            for row in candidates:
                event = {
                    "symbols": list(symbols),
                    "cik": cik,
                    "company": company_name,
                    **row,
                }
                events.append(event)

                print(
                    " ",
                    row.get("filingDate"),
                    "| accepted =", row.get("acceptanceDateTime"),
                    "| report =", row.get("reportDate"),
                    "| items =", row.get("items"),
                    "| accession =", row.get("accessionNumber"),
                    "| doc =", row.get("primaryDocument"),
                )

            # Well below SEC's published request-rate ceiling.
            await asyncio.sleep(0.35)

    covered = set()
    for event in events:
        covered.update(event["symbols"])

    missing = [
        symbol
        for symbol in COMPANIES
        if symbol not in covered
    ]

    print()
    print("=== COVERAGE SUMMARY ===")
    print(
        "tracked symbols with SEC earnings 8-K =",
        len(covered),
        "/",
        len(COMPANIES),
    )
    print("SEC Item2.02 events Jul-Aug =", len(events))
    print("missing symbols =", missing)
    print("request failures =", failed)

    by_date = defaultdict(list)
    for event in events:
        by_date[event["filingDate"]].append(
            "/".join(event["symbols"])
        )

    print()
    print("=== EVENTS BY DATE ===")
    for day in sorted(by_date):
        print(day, "=", ", ".join(sorted(by_date[day])))

    print()
    print("=== SEC EARNINGS COVERAGE AUDIT V2 COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
