import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from fia.providers import ProviderHub

load_dotenv()

START = datetime(2025, 9, 1, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)

OUTDIR = Path("fia_backtest_phase20/data")
CACHE_PATH = OUTDIR / "polygon_news_20250901_20260831.json"

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

    for attempt in range(1, 13):
        try:
            response = await client.get(
                "https://api.polygon.io/v2/reference/news",
                params=params,
            )
        except Exception as exc:
            if attempt == 12:
                raise RuntimeError(
                    f"Network failure {start} -> {end}: {exc}"
                )
            await asyncio.sleep(min(60, 5 * attempt))
            continue

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after)
            except Exception:
                delay = min(90, 12 * attempt)

            print(
                "RATE LIMIT | same historical window will retry |",
                start.date(),
                "->",
                end.date(),
            )
            await asyncio.sleep(max(1.0, delay))
            continue

        if response.status_code != 200:
            raise RuntimeError(
                f"HTTP {response.status_code} {start} -> {end}: "
                f"{response.text[:300]}"
            )

        payload = response.json()
        rows = payload.get("results") or []
        return rows if isinstance(rows, list) else []

    raise RuntimeError(
        f"Repeated rate limit for {start} -> {end}"
    )


async def fetch_complete_window(client, key, start, end):
    rows = await request_window(client, key, start, end)

    print(
        "WINDOW",
        start.isoformat(),
        "->",
        end.isoformat(),
        "| rows =",
        len(rows),
    )

    # Never follow Polygon next_url for historical replay.
    # If limit is hit, split the SAME bounded time interval.
    if len(rows) >= MAX_RESULTS:
        seconds = (end - start).total_seconds()

        if seconds <= 3600:
            raise RuntimeError(
                "A <=1h historical window still returned 1000 rows."
            )

        middle = start + (end - start) / 2

        left = await fetch_complete_window(
            client, key, start, middle
        )
        right = await fetch_complete_window(
            client, key, middle, end
        )

        merged = {}
        for article in left + right:
            merged[article_key(article)] = article

        return list(merged.values())

    return rows


def load_existing():
    if not CACHE_PATH.exists():
        return {}, [], START

    try:
        payload = json.loads(
            CACHE_PATH.read_text(encoding="utf-8")
        )
    except Exception:
        return {}, [], START

    articles = {}
    for article in payload.get("articles") or []:
        articles[article_key(article)] = article

    windows = payload.get("windows") or []

    if not windows:
        return articles, windows, START

    try:
        last_end = datetime.fromisoformat(
            windows[-1]["end"].replace("Z", "+00:00")
        )
        if last_end.tzinfo is None:
            last_end = last_end.replace(tzinfo=timezone.utc)
        resume_at = last_end.astimezone(timezone.utc) + timedelta(seconds=1)
    except Exception:
        resume_at = START

    return articles, windows, max(START, resume_at)


def save_cache(articles, windows):
    CACHE_PATH.write_text(
        json.dumps(
            {
                "start": START.isoformat(),
                "end": END.isoformat(),
                "provider": "Polygon",
                "pagination_mode": (
                    "fixed_time_windows_no_next_url"
                ),
                "articles": list(articles.values()),
                "windows": windows,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


async def main():
    hub = ProviderHub()
    key = str(
        hub.keys.get("POLYGON_API_KEY") or ""
    ).strip()

    if not key:
        raise SystemExit(
            "POLYGON_API_KEY is missing in .env"
        )

    OUTDIR.mkdir(parents=True, exist_ok=True)

    articles, windows, current = load_existing()

    print("=== PHASE 20 ONE-YEAR POLYGON ARCHIVE ===")
    print("start =", START.isoformat())
    print("end =", END.isoformat())
    print("existing articles =", len(articles))
    print("completed windows =", len(windows))
    print("resume from =", current.isoformat())
    print()

    if current > END:
        print("Archive already complete.")
    else:
        async with httpx.AsyncClient(timeout=30) as client:
            while current < END:
                window_end = min(
                    current
                    + timedelta(days=WINDOW_DAYS)
                    - timedelta(seconds=1),
                    END,
                )

                rows = await fetch_complete_window(
                    client,
                    key,
                    current,
                    window_end,
                )

                for article in rows:
                    articles[article_key(article)] = article

                windows.append(
                    {
                        "start": current.isoformat(),
                        "end": window_end.isoformat(),
                        "rows": len(rows),
                    }
                )

                # Progress survives interruption.
                save_cache(articles, windows)

                print(
                    "SAVED | windows =",
                    len(windows),
                    "| total unique articles =",
                    len(articles),
                )
                print()

                current = window_end + timedelta(seconds=1)

    # Coverage validation.
    counts = {}
    for article in articles.values():
        day = str(
            article.get("published_utc") or ""
        )[:10]
        if day:
            counts[day] = counts.get(day, 0) + 1

    zero_weekdays = []
    day = START.date()

    while day <= END.date():
        if day.weekday() < 5:
            key_day = day.isoformat()
            if counts.get(key_day, 0) == 0:
                zero_weekdays.append(key_day)
        day += timedelta(days=1)

    dates = sorted(counts)

    print("=== PHASE 20 POLYGON CACHE SUMMARY ===")
    print("articles =", len(articles))
    print("windows =", len(windows))
    print(
        "min_date =",
        dates[0] if dates else None,
    )
    print(
        "max_date =",
        dates[-1] if dates else None,
    )
    print(
        "weekday_zero_count =",
        len(zero_weekdays),
    )
    print(
        "weekday_zero_dates =",
        zero_weekdays,
    )
    print("cache =", CACHE_PATH)
    print("=== PHASE 20 NEWS CACHE COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
