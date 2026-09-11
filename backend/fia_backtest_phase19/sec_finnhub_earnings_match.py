import asyncio
import json
import math
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from fia.providers import ProviderHub
from fia.artifact_guard import guarded_output_path

load_dotenv()

START = datetime(2026, 7, 1, tzinfo=timezone.utc)
END = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)

POLYGON_CACHE = Path(
    "fia_backtest_phase19/data/polygon_news_20260628_20260831.json"
)
OUT_PATH = Path(
    "fia_backtest_phase19/data/earnings_events_sec_verified.json"
)

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

ALIASES = {
    "NVDA": ("nvidia", "nvda"),
    "MSFT": ("microsoft", "msft"),
    "AAPL": ("apple", "aapl"),
    "AMZN": ("amazon", "amzn"),
    "META": ("meta platforms", "meta", "facebook"),
    "AVGO": ("broadcom", "avgo"),
    "GOOGL": ("alphabet", "google", "googl"),
    "GOOG": ("alphabet", "google", "goog"),
    "TSLA": ("tesla", "tsla"),
    "NFLX": ("netflix", "nflx"),
    "AMD": ("advanced micro devices", "amd"),
    "MU": ("micron", "mu"),
    "INTC": ("intel", "intc"),
    "QCOM": ("qualcomm", "qcom"),
    "SMCI": ("super micro computer", "supermicro", "smci"),
}

EARNINGS_WORDS = (
    "earnings",
    "quarterly results",
    "financial results",
    "eps",
    "earnings per share",
    "revenue",
    "beats estimates",
    "misses estimates",
)

USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "CLEAR-NASDAQ-FIA historical-backtest",
).strip()

SEC_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json,text/plain,*/*",
}


def parse_dt(value):
    if not value:
        return None
    try:
        raw = str(value)
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        # SEC acceptanceDateTime may be YYYY-MM-DDTHH:MM:SS.ffffffZ
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def safe_get(values, index, default=None):
    try:
        return values[index]
    except Exception:
        return default


def company_in_article(symbol, article):
    text = (
        str(article.get("title") or "")
        + " "
        + str(article.get("description") or "")
    ).lower()

    tickers = set(article.get("tickers") or [])
    if symbol in tickers:
        return True

    return any(
        re.search(r"\b" + re.escape(alias) + r"\b", text)
        for alias in ALIASES[symbol]
    )


def numeric_variants(value):
    try:
        x = float(value)
    except Exception:
        return []

    variants = {
        f"{x:.4f}".rstrip("0").rstrip("."),
        f"{x:.3f}".rstrip("0").rstrip("."),
        f"{x:.2f}",
        f"{x:.1f}",
    }
    return [v for v in variants if "." in v and len(v) >= 3]


def actual_number_seen(value, article):
    text = (
        str(article.get("title") or "")
        + " "
        + str(article.get("description") or "")
    ).lower().replace(",", "")

    for variant in numeric_variants(value):
        if re.search(
            r"(?<!\d)" + re.escape(variant) + r"(?!\d)",
            text,
        ):
            return True
    return False


def load_polygon():
    payload = json.loads(POLYGON_CACHE.read_text(encoding="utf-8"))
    rows = payload.get("articles") or []
    prepared = []

    for article in rows:
        dt = parse_dt(article.get("published_utc"))
        if dt is None:
            continue
        item = dict(article)
        item["_dt"] = dt
        prepared.append(item)

    return prepared


async def fetch_sec_events():
    # Alphabet's CIK is fetched once.
    cik_to_symbols = defaultdict(list)
    for symbol, cik in COMPANIES.items():
        cik_to_symbols[cik].append(symbol)

    events = []

    async with httpx.AsyncClient(
        follow_redirects=True,
        http2=False,
    ) as client:
        for cik, symbols in cik_to_symbols.items():
            cik10 = str(cik).zfill(10)
            url = f"https://data.sec.gov/submissions/CIK{cik10}.json"

            response = None
            for attempt in range(1, 5):
                response = await client.get(
                    url,
                    headers=SEC_HEADERS,
                    timeout=30,
                )
                if response.status_code == 200:
                    break
                if response.status_code in (403, 429):
                    await asyncio.sleep(2 * attempt)
                    continue
                break

            if response is None or response.status_code != 200:
                print(
                    "SEC SKIP",
                    "/".join(symbols),
                    "| status =",
                    None if response is None else response.status_code,
                )
                continue

            payload = response.json()
            recent = payload.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])

            for i, form in enumerate(forms):
                if form not in ("8-K", "8-K/A"):
                    continue

                filing_date = safe_get(
                    recent.get("filingDate", []), i
                )
                if not filing_date or not (
                    START.date().isoformat()
                    <= filing_date
                    <= END.date().isoformat()
                ):
                    continue

                items = str(
                    safe_get(recent.get("items", []), i, "")
                    or ""
                )
                if "2.02" not in items:
                    continue

                accepted = parse_dt(
                    safe_get(
                        recent.get("acceptanceDateTime", []),
                        i,
                    )
                )
                if accepted is None:
                    continue

                events.append({
                    "symbols": list(symbols),
                    "company": payload.get("name"),
                    "cik": cik,
                    "accepted_at": accepted,
                    "filing_date": filing_date,
                    "report_date": safe_get(
                        recent.get("reportDate", []), i
                    ),
                    "accession": safe_get(
                        recent.get("accessionNumber", []), i
                    ),
                    "primary_document": safe_get(
                        recent.get("primaryDocument", []), i
                    ),
                    "items": items,
                })

            await asyncio.sleep(0.35)

    return events


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
        *(one(symbol) for symbol in COMPANIES),
        return_exceptions=True,
    )

    out = {}
    for result in responses:
        if isinstance(result, Exception):
            continue
        symbol, rows = result
        out[symbol] = [
            row
            for row in rows
            if int(row.get("year") or 0) == 2026
        ]

    return out


def nearby_news_score(symbol, accepted_at, actual, polygon):
    start = accepted_at - timedelta(hours=8)
    end = accepted_at + timedelta(hours=18)

    relevant = []
    earnings_relevant = []
    actual_confirmed = False

    for article in polygon:
        dt = article["_dt"]
        if not (start <= dt <= end):
            continue
        if not company_in_article(symbol, article):
            continue

        relevant.append(article)

        text = (
            str(article.get("title") or "")
            + " "
            + str(article.get("description") or "")
        ).lower()

        if any(word in text for word in EARNINGS_WORDS):
            earnings_relevant.append(article)

        if actual_number_seen(actual, article):
            actual_confirmed = True

    # SEC Item 2.02 is already strong evidence; nearby market news is used
    # only to choose between multiple plausible SEC events.
    score = (
        len(earnings_relevant) * 3
        + len(relevant)
        + (8 if actual_confirmed else 0)
    )

    samples = [
        str(a.get("title") or "")
        for a in earnings_relevant[:5]
        if a.get("title")
    ]

    return {
        "score": score,
        "nearby_company_articles": len(relevant),
        "nearby_earnings_articles": len(earnings_relevant),
        "actual_eps_seen_in_news": actual_confirmed,
        "sample_titles": samples,
    }


def match_symbol(symbol, sec_events, surprises, polygon):
    symbol_sec = [
        event
        for event in sec_events
        if symbol in event["symbols"]
    ]

    matches = []
    unmatched = []

    # Oldest period first so each SEC event can only be used once.
    rows = sorted(
        surprises,
        key=lambda r: str(r.get("period") or ""),
    )
    used_accessions = set()

    for surprise in rows:
        period = parse_dt(
            str(surprise.get("period") or "")
            + "T00:00:00+00:00"
        )
        if period is None:
            unmatched.append((surprise, "bad_period"))
            continue

        candidates = []

        for event in symbol_sec:
            if event["accession"] in used_accessions:
                continue

            lag = (
                event["accepted_at"].date()
                - period.date()
            ).days

            # Excludes events such as Tesla delivery 8-K only 2 days
            # after quarter end, while covering normal earnings lags.
            if lag < 10 or lag > 90:
                continue

            news = nearby_news_score(
                symbol,
                event["accepted_at"],
                surprise.get("actual"),
                polygon,
            )

            # Timing preference around 30-35 days, but SEC + news evidence
            # dominates the ranking.
            timing_penalty = abs(lag - 32) / 8.0
            rank = news["score"] - timing_penalty

            candidates.append(
                (rank, news["score"], -abs(lag - 32), event, lag, news)
            )

        if not candidates:
            unmatched.append(
                (surprise, "no_plausible_sec_item_2_02")
            )
            continue

        candidates.sort(
            key=lambda row: (
                row[0],
                row[1],
                row[2],
                row[3]["accepted_at"],
            ),
            reverse=True,
        )

        _, _, _, event, lag, news = candidates[0]
        used_accessions.add(event["accession"])

        try:
            actual = float(surprise.get("actual"))
            estimate = float(surprise.get("estimate"))
            direction = (
                "BULLISH"
                if actual > estimate
                else "BEARISH"
                if actual < estimate
                else "NEUTRAL"
            )
        except Exception:
            direction = "NEUTRAL"

        matches.append({
            "symbol": symbol,
            "period": surprise.get("period"),
            "year": surprise.get("year"),
            "quarter": surprise.get("quarter"),
            "actual": surprise.get("actual"),
            "estimate": surprise.get("estimate"),
            "surprise_percent": surprise.get("surprisePercent"),
            "surprise_direction": direction,
            "reveal_at": event["accepted_at"].isoformat(),
            "filing_date": event["filing_date"],
            "report_date": event["report_date"],
            "sec_accession": event["accession"],
            "sec_primary_document": event["primary_document"],
            "sec_items": event["items"],
            "quarter_end_to_sec_days": lag,
            "nearby_company_articles": news["nearby_company_articles"],
            "nearby_earnings_articles": news["nearby_earnings_articles"],
            "actual_eps_seen_in_news": news["actual_eps_seen_in_news"],
            "sample_titles": news["sample_titles"],
            "verification": (
                "SEC Item 2.02 acceptance timestamp gates Finnhub "
                "actual/estimate; actual is never active before reveal_at."
            ),
        })

    return matches, unmatched


def dedupe_alphabet(events):
    result = []
    seen = set()

    for event in sorted(events, key=lambda e: e["reveal_at"]):
        if event["symbol"] in ("GOOG", "GOOGL"):
            key = (
                event["period"],
                event["sec_accession"],
            )
            if key in seen:
                continue
            seen.add(key)
            event = dict(event)
            event["symbol"] = "ALPHABET"

        result.append(event)

    return result


async def main():
    if not POLYGON_CACHE.exists():
        raise SystemExit(
            f"Missing Polygon cache: {POLYGON_CACHE}"
        )

    hub = ProviderHub()

    print("=== PHASE 19 SEC + FINNHUB EARNINGS MATCH ===")

    polygon = load_polygon()
    sec_events = await fetch_sec_events()
    surprises = await fetch_surprises(hub)

    print("SEC Item2.02 events =", len(sec_events))
    print("Polygon cached articles =", len(polygon))
    print()

    all_matches = []
    all_unmatched = []

    for symbol in COMPANIES:
        matches, unmatched = match_symbol(
            symbol,
            sec_events,
            surprises.get(symbol, []),
            polygon,
        )
        all_matches.extend(matches)

        for row, reason in unmatched:
            all_unmatched.append({
                "symbol": symbol,
                "period": row.get("period"),
                "quarter": row.get("quarter"),
                "actual": row.get("actual"),
                "estimate": row.get("estimate"),
                "reason": reason,
            })

    all_matches = dedupe_alphabet(all_matches)
    all_matches.sort(key=lambda e: e["reveal_at"])

    jul_aug = [
        event
        for event in all_matches
        if START <= parse_dt(event["reveal_at"]) <= END
    ]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # A6: sealed-artifact guard. This output is registered canonical
    # evidence, so a default run writes to a per-run directory instead.
    guarded_output_path(OUT_PATH).write_text(
        json.dumps(
            {
                "method": (
                    "SEC 8-K Item 2.02 acceptance timestamp + Finnhub "
                    "quarterly EPS surprise. Polygon historical news is "
                    "used only to resolve ambiguous SEC-event matches."
                ),
                "events": all_matches,
                "unmatched": all_unmatched,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("matched_2026 =", len(all_matches))
    print("jul_aug_verified_events =", len(jul_aug))
    print("unmatched =", len(all_unmatched))
    print("cache =", OUT_PATH)
    print()

    print("=== VERIFIED JUL-AUG EVENTS ===")
    for event in jul_aug:
        print(
            event["filing_date"],
            "|", event["symbol"],
            "| EPS", event["actual"], "vs", event["estimate"],
            "| surprise =", event["surprise_direction"],
            "| reveal =", event["reveal_at"],
            "| lag =", event["quarter_end_to_sec_days"], "days",
            "| news =", event["nearby_earnings_articles"],
            "| actual_seen =", event["actual_eps_seen_in_news"],
        )

    print()
    print("=== UNMATCHED BY SYMBOL ===")
    counts = defaultdict(int)
    for row in all_unmatched:
        counts[row["symbol"]] += 1

    for symbol in COMPANIES:
        if counts[symbol]:
            print(symbol, "=", counts[symbol])

    print()
    print("=== SEC + FINNHUB EARNINGS MATCH COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
