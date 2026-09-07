import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from fia.providers import ProviderHub

load_dotenv()

START = datetime(2026, 6, 28, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)

OUTDIR = Path("fia_backtest_phase19/data")
CACHE_PATH = OUTDIR / "polygon_news_20260628_20260831.json"
WINDOW_DAYS = 4
MAX_RESULTS = 1000


def article_key(article):
    return str(
        article.get("id")
        or article.get("article_url")
        or (
            str(article.get("published_utc") or "")
            + "|"
            + str(article.get("title") or "")
        )
    )


async def request_window(client, key, start, end):
    params = {
        "published_utc.gte": start.isoformat(),
        "published_utc.lte": end.isoformat(),
        "order": "asc",
        "sort": "published_utc",
        "limit": MAX_RESULTS,
        "apiKey": key,
    }

    attempt = 0
    while True:
        attempt += 1

        try:
            response = await client.get(
                "https://api.polygon.io/v2/reference/news",
                params=params,
            )
        except Exception as exc:
            if attempt >= 8:
                raise RuntimeError(
                    f"Network failure for {start} -> {end}: {exc}"
                )
            await asyncio.sleep(min(60, 5 * attempt))
            continue

        if response.status_code == 429:
            if attempt >= 12:
                raise RuntimeError(
                    f"Repeated HTTP 429 for {start} -> {end}"
                )

            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after)
            except Exception:
                delay = min(60, 12 * attempt)

            print(
                "RATE LIMIT | retrying same historical window",
                start.date(),
                "->",
                end.date(),
            )
            await asyncio.sleep(max(1.0, delay))
            continue

        if response.status_code != 200:
            raise RuntimeError(
                f"HTTP {response.status_code} for {start} -> {end}: "
                f"{response.text[:300]}"
            )

        payload = response.json()
        rows = payload.get("results") or []

        if not isinstance(rows, list):
            rows = []

        return rows


async def fetch_complete_window(client, key, start, end, depth=0):
    rows = await request_window(client, key, start, end)

    print(
        "WINDOW",
        start.isoformat(),
        "->",
        end.isoformat(),
        "| rows =",
        len(rows),
    )

    # If the endpoint hit its 1000-row ceiling, do NOT follow next_url.
    # Split the same locked historical interval into smaller intervals.
    if len(rows) >= MAX_RESULTS:
        total_seconds = (end - start).total_seconds()

        if total_seconds <= 3600:
            raise RuntimeError(
                "A <=1 hour window still hit 1000 rows; cannot guarantee completeness."
            )

        midpoint = start + (end - start) / 2

        left = await fetch_complete_window(
            client,
            key,
            start,
            midpoint,
            depth + 1,
        )
        right = await fetch_complete_window(
            client,
            key,
            midpoint,
            end,
            depth + 1,
        )

        merged = {}
        for article in left + right:
            merged[article_key(article)] = article

        return list(merged.values())

    return rows


async def main():
    hub = ProviderHub()
    key = str(hub.keys.get("POLYGON_API_KEY") or "").strip()

    if not key:
        raise SystemExit("POLYGON_API_KEY is missing in .env")

    OUTDIR.mkdir(parents=True, exist_ok=True)

    all_articles = {}
    window_summary = []

    async with httpx.AsyncClient(timeout=30) as client:
        current = START
        index = 0

        while current < END:
            index += 1
            window_end = min(
                current + timedelta(days=WINDOW_DAYS) - timedelta(seconds=1),
                END,
            )

            print()
            print(
                f"=== ARCHIVE WINDOW {index} ===",
                current.isoformat(),
                "->",
                window_end.isoformat(),
            )

            rows = await fetch_complete_window(
                client,
                key,
                current,
                window_end,
            )

            for article in rows:
                all_articles[article_key(article)] = article

            window_summary.append(
                {
                    "start": current.isoformat(),
                    "end": window_end.isoformat(),
                    "rows": len(rows),
                }
            )

            # Save after every completed window so progress is not lost.
            CACHE_PATH.write_text(
                json.dumps(
                    {
                        "start": START.isoformat(),
                        "end": END.isoformat(),
                        "provider": "Polygon",
                        "pagination_mode": "fixed_time_windows_no_next_url",
                        "articles": list(all_articles.values()),
                        "windows": window_summary,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            current = window_end + timedelta(seconds=1)

    articles = list(all_articles.values())
    dates = sorted(
        {
            str(a.get("published_utc") or "")[:10]
            for a in articles
            if a.get("published_utc")
        }
    )

    print()
    print("=== POLYGON ARCHIVE CACHE COMPLETE ===")
    print("articles =", len(articles))
    print("windows =", len(window_summary))
    print("min_date =", dates[0] if dates else None)
    print("max_date =", dates[-1] if dates else None)
    print("cache =", CACHE_PATH)

    # Coverage check for every weekday in Jul-Aug.
    counts = {}
    for article in articles:
        day = str(article.get("published_utc") or "")[:10]
        if day:
            counts[day] = counts.get(day, 0) + 1

    zero_days = []
    day = datetime(2026, 7, 1, tzinfo=timezone.utc).date()
    last = datetime(2026, 8, 31, tzinfo=timezone.utc).date()

    print()
    print("=== WEEKDAY POLYGON COVERAGE ===")
    while day <= last:
        if day.weekday() < 5:
            key_day = day.isoformat()
            count = counts.get(key_day, 0)
            if count == 0:
                zero_days.append(key_day)
            print(key_day, "=", count)
        day += timedelta(days=1)

    print()
    print("weekday_zero_count =", len(zero_days))
    print("weekday_zero_dates =", zero_days)
    print("=== CACHE BUILD COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
