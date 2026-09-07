import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

from fia.providers import ProviderHub
from fia_backtest_phase19.full_snapshot import SYMBOLS, normalize_article, normalize_timestamp

load_dotenv()

START = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)


def day_key(value):
    try:
        return normalize_timestamp(value).date().isoformat()
    except Exception:
        return None


async def polygon_archive(hub):
    key = hub.keys.get("POLYGON_API_KEY")
    if not key:
        return [], [], "MISSING_KEY"

    url = "https://api.polygon.io/v2/reference/news"
    params = {
        "published_utc.gte": (START - timedelta(days=3)).isoformat(),
        "published_utc.lte": END.isoformat(),
        "order": "asc",
        "sort": "published_utc",
        "limit": 1000,
        "apiKey": key,
    }

    rows = []
    page_meta = []

    async with httpx.AsyncClient(timeout=30) as client:
        for page_no in range(1, 101):
            try:
                response = await client.get(url, params=params)
                status = response.status_code
                if status != 200:
                    return rows, page_meta, f"HTTP_{status}"
                payload = response.json()
            except Exception as exc:
                return rows, page_meta, f"ERROR_{type(exc).__name__}"

            batch = payload.get("results") or []
            stamps = [
                r.get("published_utc")
                for r in batch
                if isinstance(r, dict) and r.get("published_utc")
            ]

            page_meta.append({
                "page": page_no,
                "count": len(batch),
                "first": stamps[0] if stamps else None,
                "last": stamps[-1] if stamps else None,
            })
            rows.extend(batch)

            next_url = payload.get("next_url")
            if not next_url:
                return rows, page_meta, "OK"

            url = next_url
            params = {"apiKey": key}

    return rows, page_meta, "PAGE_LIMIT"


async def finnhub_archive(hub):
    key = hub.keys.get("FINNHUB_API_KEY")
    if not key:
        return [], {}, "MISSING_KEY"

    start = (START - timedelta(days=3)).date().isoformat()
    end = END.date().isoformat()

    async def one(symbol):
        payload = await hub.get(
            "https://finnhub.io/api/v1/company-news",
            {
                "symbol": symbol,
                "from": start,
                "to": end,
                "token": key,
            },
            timeout=30,
        )
        items = []
        for a in payload if isinstance(payload, list) else []:
            item = normalize_article(a, "Finnhub", "company", symbol)
            if item:
                items.append(item)
        return symbol, items

    responses = await asyncio.gather(
        *(one(symbol) for symbol in SYMBOLS),
        return_exceptions=True,
    )

    all_items = []
    per_symbol = {}

    for result in responses:
        if isinstance(result, Exception):
            continue
        symbol, items = result
        per_symbol[symbol] = len(items)
        all_items.extend(items)

    return all_items, per_symbol, "OK"


async def main():
    hub = ProviderHub()

    print("=== PHASE 19 NEWS COVERAGE AUDIT ===")
    print("window =", START.isoformat(), "->", END.isoformat())
    print()

    polygon_rows, pages, polygon_status = await polygon_archive(hub)

    print("=== POLYGON ARCHIVE ===")
    print("status =", polygon_status)
    print("pages =", len(pages))
    print("rows =", len(polygon_rows))
    for meta in pages:
        print(
            "page", meta["page"],
            "| n =", meta["count"],
            "| first =", meta["first"],
            "| last =", meta["last"],
        )
    print()

    polygon_counts = Counter()
    for row in polygon_rows:
        d = day_key(row.get("published_utc"))
        if d:
            polygon_counts[d] += 1

    finnhub_rows, finnhub_symbols, finnhub_status = await finnhub_archive(hub)

    print("=== FINNHUB ARCHIVE ===")
    print("status =", finnhub_status)
    print("rows =", len(finnhub_rows))
    print("per_symbol =", finnhub_symbols)
    print()

    finnhub_counts = Counter()
    for row in finnhub_rows:
        d = day_key(row.get("published_at"))
        if d:
            finnhub_counts[d] += 1

    print("=== DAILY COVERAGE ===")
    current = START.date()
    end_date = END.date()
    zero_combined = []

    while current <= end_date:
        day = current.isoformat()
        p = polygon_counts.get(day, 0)
        f = finnhub_counts.get(day, 0)
        total = p + f

        if current.weekday() < 5:
            marker = "ZERO" if total == 0 else ""
            print(
                day,
                "| Polygon =", p,
                "| Finnhub =", f,
                "| Combined =", total,
                marker,
            )
            if total == 0:
                zero_combined.append(day)

        current += timedelta(days=1)

    print()
    print("=== GAP SUMMARY ===")
    print("weekday_zero_count =", len(zero_combined))
    print("weekday_zero_dates =", zero_combined)

    polygon_dates = sorted(polygon_counts)
    finnhub_dates = sorted(finnhub_counts)

    print(
        "polygon_min_date =",
        polygon_dates[0] if polygon_dates else None,
        "| polygon_max_date =",
        polygon_dates[-1] if polygon_dates else None,
    )
    print(
        "finnhub_min_date =",
        finnhub_dates[0] if finnhub_dates else None,
        "| finnhub_max_date =",
        finnhub_dates[-1] if finnhub_dates else None,
    )

    print("=== NEWS COVERAGE AUDIT COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
