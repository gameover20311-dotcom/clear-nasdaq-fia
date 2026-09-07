import asyncio
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from fia.providers import ProviderHub

load_dotenv()

SYMBOLS = [
    "NVDA","MSFT","AAPL","AMZN","META","AVGO","GOOGL","GOOG",
    "TSLA","NFLX","AMD","MU","INTC","QCOM","SMCI",
]

CACHE_PATH = Path(
    "fia_backtest_phase19/data/polygon_news_20260628_20260831.json"
)

EARNINGS_TERMS = (
    "earnings",
    "quarterly results",
    "reports results",
    "reported results",
    "eps",
    "revenue",
)

GUIDANCE_TERMS = (
    "guidance",
    "outlook",
    "forecast",
    "raises guidance",
    "cuts guidance",
    "raises outlook",
    "lowers outlook",
)


def parse_polygon_time(article):
    raw = article.get("published_utc")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(
            str(raw).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except Exception:
        return None


def text_blob(article):
    return (
        str(article.get("title") or "")
        + " "
        + str(article.get("description") or "")
    ).lower()


def polygon_earnings_candidates():
    if not CACHE_PATH.exists():
        raise FileNotFoundError(
            f"Missing Polygon cache: {CACHE_PATH}"
        )

    payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    rows = payload.get("articles") or []

    by_symbol = defaultdict(list)

    for article in rows:
        dt = parse_polygon_time(article)
        if dt is None:
            continue

        tickers = set(article.get("tickers") or [])
        blob = text_blob(article)

        event_kind = None
        if any(term in blob for term in EARNINGS_TERMS):
            event_kind = "earnings"
        elif any(term in blob for term in GUIDANCE_TERMS):
            event_kind = "guidance"

        if not event_kind:
            continue

        for symbol in SYMBOLS:
            if symbol in tickers:
                by_symbol[symbol].append({
                    "published_at": dt.isoformat(),
                    "kind": event_kind,
                    "title": article.get("title"),
                    "source": (
                        (article.get("publisher") or {}).get("name")
                        if isinstance(article.get("publisher"), dict)
                        else ""
                    ),
                })

    for symbol in by_symbol:
        by_symbol[symbol].sort(key=lambda x: x["published_at"])

    return by_symbol


async def finnhub_surprises(hub):
    key = hub.keys.get("FINNHUB_API_KEY")
    if not key:
        return {}, {"status": "MISSING_KEY"}

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

    results = await asyncio.gather(
        *(one(symbol) for symbol in SYMBOLS),
        return_exceptions=True,
    )

    out = {}

    for result in results:
        if isinstance(result, Exception):
            continue
        symbol, rows = result
        out[symbol] = rows

    return out, {"status": "OK"}


async def calendar_probe(hub):
    key = hub.keys.get("FINNHUB_API_KEY")
    if not key:
        return []

    payload = await hub.get(
        "https://finnhub.io/api/v1/calendar/earnings",
        {
            "from": "2026-07-01",
            "to": "2026-08-31",
            "token": key,
        },
        timeout=20,
    )

    rows = (payload or {}).get("earningsCalendar", [])
    return [
        r for r in rows
        if r.get("symbol") in set(SYMBOLS)
    ]


async def main():
    hub = ProviderHub()

    polygon = polygon_earnings_candidates()
    surprises, surprise_meta = await finnhub_surprises(hub)
    calendar = await calendar_probe(hub)

    print("=== PHASE 19 EARNINGS SOURCE AUDIT ===")
    print("polygon cache =", CACHE_PATH)
    print("finnhub surprise status =", surprise_meta["status"])
    print()

    print("=== FINNHUB WIDE CALENDAR PROBE ===")
    print("tracked calendar events =", len(calendar))
    for row in calendar:
        print(
            row.get("date"),
            "|", row.get("symbol"),
            "| hour =", row.get("hour"),
            "| epsActual =", row.get("epsActual"),
            "| epsEstimate =", row.get("epsEstimate"),
        )
    print()

    print("=== SYMBOL COVERAGE ===")

    symbols_with_2026_surprise = 0
    symbols_with_polygon_candidates = 0

    for symbol in SYMBOLS:
        rows = surprises.get(symbol, [])
        rows_2026 = [
            r for r in rows
            if int(r.get("year") or 0) == 2026
        ]

        candidates = polygon.get(symbol, [])

        if rows_2026:
            symbols_with_2026_surprise += 1
        if candidates:
            symbols_with_polygon_candidates += 1

        print()
        print(symbol)
        print("  finnhub_surprises_2026 =", len(rows_2026))

        for r in rows_2026:
            print(
                "   ",
                "period =", r.get("period"),
                "| q =", r.get("quarter"),
                "| actual =", r.get("actual"),
                "| estimate =", r.get("estimate"),
                "| surprisePct =", r.get("surprisePercent"),
            )

        print("  polygon_earnings_guidance_articles =", len(candidates))

        for c in candidates[:8]:
            print(
                "   ",
                c["published_at"],
                "|", c["kind"],
                "|", str(c["title"])[:130],
            )

    print()
    print("=== SUMMARY ===")
    print(
        "symbols_with_2026_finnhub_surprise =",
        symbols_with_2026_surprise,
        "/",
        len(SYMBOLS),
    )
    print(
        "symbols_with_polygon_earnings_guidance =",
        symbols_with_polygon_candidates,
        "/",
        len(SYMBOLS),
    )
    print(
        "total_polygon_earnings_guidance_articles =",
        sum(len(v) for v in polygon.values()),
    )

    print()
    print("=== EARNINGS SOURCE AUDIT COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
