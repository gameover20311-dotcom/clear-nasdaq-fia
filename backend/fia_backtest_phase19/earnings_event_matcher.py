import asyncio
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from fia.providers import ProviderHub

load_dotenv()

SYMBOLS = [
    "NVDA","MSFT","AAPL","AMZN","META","AVGO","GOOGL","GOOG",
    "TSLA","NFLX","AMD","MU","INTC","QCOM","SMCI",
]

POLYGON_CACHE = Path(
    "fia_backtest_phase19/data/polygon_news_20260628_20260831.json"
)
OUT_PATH = Path(
    "fia_backtest_phase19/data/earnings_events_2026.json"
)

PREVIEW_TERMS = (
    "earnings preview",
    "ahead of earnings",
    "ahead of its earnings",
    "before earnings",
    "before its earnings",
    "will report",
    "set to report",
    "expected to report",
    "scheduled to report",
    "earnings date",
    "what to expect",
    "options imply",
    "earnings expected",
)

STRONG_RELEASE_TERMS = (
    "quarterly results",
    "earnings results",
    "reports earnings",
    "reported earnings",
    "reports revenue",
    "reported revenue",
    "beats estimates",
    "beat estimates",
    "misses estimates",
    "missed estimates",
    "eps of",
    "eps ",
    "revenue of",
    "announces results",
    "announced results",
)

GUIDANCE_BULL = (
    "raises guidance",
    "raised guidance",
    "raises outlook",
    "raised outlook",
    "boosts guidance",
    "boosted guidance",
    "guidance above",
    "outlook above",
)

GUIDANCE_BEAR = (
    "cuts guidance",
    "cut guidance",
    "lowers guidance",
    "lowered guidance",
    "cuts outlook",
    "cut outlook",
    "guidance below",
    "outlook below",
)


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except Exception:
        return None


def text(article):
    return (
        str(article.get("title") or "")
        + " "
        + str(article.get("description") or "")
    ).lower()


def release_strength(article):
    blob = text(article)

    if any(term in blob for term in PREVIEW_TERMS):
        return 0

    score = 0

    for term in STRONG_RELEASE_TERMS:
        if term in blob:
            score += 2

    # Results + company financial words together are stronger evidence.
    if (
        ("reports" in blob or "reported" in blob or "results" in blob)
        and ("revenue" in blob or "earnings" in blob or "eps" in blob)
    ):
        score += 3

    if "beat estimates" in blob or "beats estimates" in blob:
        score += 3

    if "missed estimates" in blob or "misses estimates" in blob:
        score += 3

    return score


def guidance_direction(articles):
    bull = 0
    bear = 0

    for article in articles:
        blob = text(article)
        bull += sum(term in blob for term in GUIDANCE_BULL)
        bear += sum(term in blob for term in GUIDANCE_BEAR)

    if bull > bear:
        return "BULLISH", bull, bear

    if bear > bull:
        return "BEARISH", bull, bear

    return "NEUTRAL", bull, bear


def load_polygon_by_symbol():
    if not POLYGON_CACHE.exists():
        raise FileNotFoundError(
            f"Missing Polygon cache: {POLYGON_CACHE}"
        )

    payload = json.loads(POLYGON_CACHE.read_text(encoding="utf-8"))
    rows = payload.get("articles") or []

    by_symbol = defaultdict(list)

    for article in rows:
        dt = parse_dt(article.get("published_utc"))
        if dt is None:
            continue

        tickers = set(article.get("tickers") or [])

        for symbol in SYMBOLS:
            if symbol in tickers:
                by_symbol[symbol].append(
                    {
                        **article,
                        "_published_dt": dt,
                    }
                )

    for symbol in by_symbol:
        by_symbol[symbol].sort(
            key=lambda a: a["_published_dt"]
        )

    return by_symbol


async def fetch_surprises(hub):
    key = hub.keys.get("FINNHUB_API_KEY")
    if not key:
        raise RuntimeError("FINNHUB_API_KEY missing")

    async def one(symbol):
        payload = await hub.get(
            "https://finnhub.io/api/v1/stock/earnings",
            {
                "symbol": symbol,
                "limit": 4,
                "token": key,
            },
            timeout=20,
        )
        return symbol, payload if isinstance(payload, list) else []

    responses = await asyncio.gather(
        *(one(symbol) for symbol in SYMBOLS),
        return_exceptions=True,
    )

    result = {}

    for item in responses:
        if isinstance(item, Exception):
            continue

        symbol, rows = item

        result[symbol] = [
            row
            for row in rows
            if int(row.get("year") or 0) == 2026
        ]

    return result


def choose_release(symbol, surprise, articles):
    period = parse_dt(
        str(surprise.get("period") or "") + "T00:00:00+00:00"
    )

    if period is None:
        return None

    # Typical US earnings are released several weeks after quarter end.
    # The broad window is only used to locate public release evidence.
    start = period + timedelta(days=10)
    end = period + timedelta(days=100)

    candidates = []

    for article in articles:
        dt = article["_published_dt"]

        if dt < start or dt > end:
            continue

        strength = release_strength(article)

        if strength <= 0:
            continue

        candidates.append(
            (dt, strength, article)
        )

    if not candidates:
        return None

    # Group release evidence by UTC date.
    by_day = defaultdict(list)

    for dt, strength, article in candidates:
        by_day[dt.date()].append(
            (dt, strength, article)
        )

    ranked_days = []

    for day, items in by_day.items():
        total_strength = sum(
            strength
            for _, strength, _ in items
        )

        strong_articles = sum(
            strength >= 3
            for _, strength, _ in items
        )

        ranked_days.append(
            (
                day,
                total_strength,
                strong_articles,
                items,
            )
        )

    # Prefer the earliest day that has convincing release evidence.
    convincing = [
        row
        for row in ranked_days
        if row[1] >= 5 or row[2] >= 2
    ]

    if convincing:
        convincing.sort(
            key=lambda row: row[0]
        )
        chosen = convincing[0]
    else:
        ranked_days.sort(
            key=lambda row: (-row[1], row[0])
        )
        chosen = ranked_days[0]

    day, total_strength, strong_articles, items = chosen

    items.sort(
        key=lambda row: row[0]
    )

    reveal_at = items[0][0]

    # Guidance evidence on release day and the following 24 hours.
    guidance_articles = [
        article
        for article in articles
        if reveal_at
        <= article["_published_dt"]
        <= reveal_at + timedelta(hours=24)
        and (
            "guidance" in text(article)
            or "outlook" in text(article)
        )
    ]

    guidance, guidance_bull, guidance_bear = guidance_direction(
        guidance_articles
    )

    titles = []
    for _, _, article in items[:6]:
        title = str(article.get("title") or "").strip()
        if title:
            titles.append(title)

    try:
        actual = float(surprise.get("actual"))
        estimate = float(surprise.get("estimate"))
    except Exception:
        actual = None
        estimate = None

    surprise_direction = "NEUTRAL"

    if actual is not None and estimate is not None:
        if actual > estimate:
            surprise_direction = "BULLISH"
        elif actual < estimate:
            surprise_direction = "BEARISH"

    return {
        "symbol": symbol,
        "year": surprise.get("year"),
        "quarter": surprise.get("quarter"),
        "period": surprise.get("period"),
        "actual": surprise.get("actual"),
        "estimate": surprise.get("estimate"),
        "surprise_percent": surprise.get("surprisePercent"),
        "surprise_direction": surprise_direction,
        "release_date": day.isoformat(),
        "reveal_at": reveal_at.isoformat(),
        "release_match_strength": total_strength,
        "release_strong_articles": strong_articles,
        "release_article_count": len(items),
        "guidance_direction": guidance,
        "guidance_bull_matches": guidance_bull,
        "guidance_bear_matches": guidance_bear,
        "guidance_article_count": len(guidance_articles),
        "sample_titles": titles,
    }


async def main():
    hub = ProviderHub()

    polygon = load_polygon_by_symbol()
    surprises = await fetch_surprises(hub)

    matched = []
    unmatched = []

    for symbol in SYMBOLS:
        for surprise in surprises.get(symbol, []):
            event = choose_release(
                symbol,
                surprise,
                polygon.get(symbol, []),
            )

            if event:
                matched.append(event)
            else:
                unmatched.append(
                    {
                        "symbol": symbol,
                        "year": surprise.get("year"),
                        "quarter": surprise.get("quarter"),
                        "period": surprise.get("period"),
                        "actual": surprise.get("actual"),
                        "estimate": surprise.get("estimate"),
                    }
                )

    matched.sort(
        key=lambda event: event["reveal_at"]
    )

    OUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUT_PATH.write_text(
        json.dumps(
            {
                "method": (
                    "Finnhub EPS actual/estimate gated by first convincing "
                    "Polygon historical release evidence; no EPS signal is "
                    "available before reveal_at."
                ),
                "events": matched,
                "unmatched": unmatched,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    jul_aug = [
        event
        for event in matched
        if "2026-07-01" <= event["release_date"] <= "2026-08-31"
    ]

    print("=== PHASE 19 POINT-IN-TIME EARNINGS MATCH ===")
    print("matched_2026 =", len(matched))
    print("unmatched_2026 =", len(unmatched))
    print("jul_aug_events =", len(jul_aug))
    print("cache =", OUT_PATH)
    print()

    print("=== JUL-AUG MATCHED EVENTS ===")

    for event in jul_aug:
        print(
            event["release_date"],
            "|",
            event["symbol"],
            "| EPS",
            event["actual"],
            "vs",
            event["estimate"],
            "| surprise =",
            event["surprise_direction"],
            "| guidance =",
            event["guidance_direction"],
            "| reveal =",
            event["reveal_at"],
            "| strength =",
            event["release_match_strength"],
        )

    print()

    if unmatched:
        print("=== UNMATCHED ===")
        for event in unmatched:
            print(
                event["symbol"],
                "| period =",
                event["period"],
                "| q =",
                event["quarter"],
            )
        print()

    print("=== EARNINGS MATCH COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
