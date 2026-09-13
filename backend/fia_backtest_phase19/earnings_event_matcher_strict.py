import asyncio
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fia.providers import ProviderHub
from fia.artifact_guard import guarded_output_path

load_dotenv()

POLYGON_CACHE = Path("fia_backtest_phase19/data/polygon_news_20260628_20260831.json")
OUT_PATH = Path("fia_backtest_phase19/data/earnings_events_2026_strict.json")

SYMBOLS = [
    "NVDA","MSFT","AAPL","AMZN","META","AVGO","GOOGL","GOOG",
    "TSLA","NFLX","AMD","MU","INTC","QCOM","SMCI",
]

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

RELEASE_PHRASES = (
    "reports earnings",
    "reported earnings",
    "quarterly results",
    "reports results",
    "reported results",
    "announces financial results",
    "announced financial results",
    "earnings results",
    "eps of",
    "earnings per share",
    "beats estimates",
    "beat estimates",
    "misses estimates",
    "missed estimates",
    "revenue of",
)

PREVIEW_PHRASES = (
    "earnings preview",
    "ahead of earnings",
    "ahead of its earnings",
    "will report",
    "set to report",
    "expected to report",
    "scheduled to report",
    "earnings date",
    "what to expect",
    "options imply",
)

GUIDANCE_BULL = (
    "raises guidance", "raised guidance", "raises outlook", "raised outlook",
    "boosts guidance", "boosted guidance", "guidance above", "outlook above",
)
GUIDANCE_BEAR = (
    "cuts guidance", "cut guidance", "lowers guidance", "lowered guidance",
    "cuts outlook", "cut outlook", "guidance below", "outlook below",
)


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def blob(article):
    return (
        str(article.get("title") or "") + " " +
        str(article.get("description") or "")
    ).lower()


def has_company(symbol, article):
    text = blob(article)
    return any(re.search(r"\b" + re.escape(alias) + r"\b", text) for alias in ALIASES[symbol])


def is_release_article(article):
    text = blob(article)
    if any(p in text for p in PREVIEW_PHRASES):
        return False
    return any(p in text for p in RELEASE_PHRASES)


def numeric_variants(value):
    try:
        x = float(value)
    except Exception:
        return []

    vals = {
        f"{x:.4f}".rstrip("0").rstrip("."),
        f"{x:.3f}".rstrip("0").rstrip("."),
        f"{x:.2f}",
        f"{x:.1f}",
    }

    # Do not keep overly-generic integer variants.
    return sorted(v for v in vals if "." in v and len(v) >= 3)


def number_present(value, article):
    text = blob(article).replace(",", "")
    for variant in numeric_variants(value):
        pattern = r"(?<!\d)" + re.escape(variant) + r"(?!\d)"
        if re.search(pattern, text):
            return True
    return False


def load_polygon():
    payload = json.loads(POLYGON_CACHE.read_text(encoding="utf-8"))
    rows = payload.get("articles") or []
    by_symbol = defaultdict(list)

    for article in rows:
        dt = parse_dt(article.get("published_utc"))
        if dt is None:
            continue

        tickers = set(article.get("tickers") or [])
        for symbol in SYMBOLS:
            if symbol in tickers or has_company(symbol, article):
                item = dict(article)
                item["_dt"] = dt
                by_symbol[symbol].append(item)

    for symbol in by_symbol:
        by_symbol[symbol].sort(key=lambda a: a["_dt"])

    return by_symbol


async def fetch_surprises(hub):
    key = hub.keys.get("FINNHUB_API_KEY")
    if not key:
        raise RuntimeError("FINNHUB_API_KEY missing")

    async def one(symbol):
        payload = await hub.get(
            "https://finnhub.io/api/v1/stock/earnings",
            {"symbol": symbol, "limit": 4, "token": key},
            timeout=20,
        )
        return symbol, payload if isinstance(payload, list) else []

    responses = await asyncio.gather(
        *(one(s) for s in SYMBOLS),
        return_exceptions=True,
    )

    out = {}
    for result in responses:
        if isinstance(result, Exception):
            continue
        symbol, rows = result
        out[symbol] = [r for r in rows if int(r.get("year") or 0) == 2026]
    return out


def guidance_from_nearby(symbol, reveal_at, articles):
    nearby = [
        a for a in articles
        if reveal_at <= a["_dt"] <= reveal_at + timedelta(hours=36)
        and has_company(symbol, a)
    ]

    bull = bear = 0
    for a in nearby:
        text = blob(a)
        bull += sum(term in text for term in GUIDANCE_BULL)
        bear += sum(term in text for term in GUIDANCE_BEAR)

    if bull > bear:
        direction = "BULLISH"
    elif bear > bull:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    return direction, bull, bear, len(nearby)


def choose_strict(symbol, surprise, articles):
    period = parse_dt(str(surprise.get("period") or "") + "T00:00:00+00:00")
    if period is None:
        return None, "bad_period"

    # Cache starts 2026-06-28. Only events whose plausible release window overlaps cache
    # can be validated here.
    start = period + timedelta(days=7)
    end = period + timedelta(days=100)

    candidates = []

    for article in articles:
        dt = article["_dt"]
        if not (start <= dt <= end):
            continue
        if not has_company(symbol, article):
            continue
        if not is_release_article(article):
            continue

        actual_match = number_present(surprise.get("actual"), article)
        estimate_match = number_present(surprise.get("estimate"), article)

        # Strict rule: actual EPS must be present. Estimate match boosts confidence.
        if not actual_match:
            continue

        score = 5 + (3 if estimate_match else 0)

        text = blob(article)
        if "quarterly results" in text or "financial results" in text:
            score += 2
        if "beats estimates" in text or "misses estimates" in text:
            score += 2

        candidates.append((dt, score, estimate_match, article))

    if not candidates:
        return None, "no_strict_release_match"

    candidates.sort(key=lambda x: (x[0], -x[1]))
    reveal_at, score, estimate_match, article = candidates[0]

    guidance, gb, gr, nearby_count = guidance_from_nearby(
        symbol, reveal_at, articles
    )

    try:
        actual = float(surprise.get("actual"))
        estimate = float(surprise.get("estimate"))
        surprise_direction = (
            "BULLISH" if actual > estimate else
            "BEARISH" if actual < estimate else
            "NEUTRAL"
        )
    except Exception:
        surprise_direction = "NEUTRAL"

    return {
        "symbol": symbol,
        "year": surprise.get("year"),
        "quarter": surprise.get("quarter"),
        "period": surprise.get("period"),
        "actual": surprise.get("actual"),
        "estimate": surprise.get("estimate"),
        "surprise_percent": surprise.get("surprisePercent"),
        "surprise_direction": surprise_direction,
        "release_date": reveal_at.date().isoformat(),
        "reveal_at": reveal_at.isoformat(),
        "strict_match_score": score,
        "estimate_number_confirmed": estimate_match,
        "guidance_direction": guidance,
        "guidance_bull_matches": gb,
        "guidance_bear_matches": gr,
        "nearby_company_articles_36h": nearby_count,
        "release_title": article.get("title"),
        "release_source": (
            (article.get("publisher") or {}).get("name")
            if isinstance(article.get("publisher"), dict)
            else ""
        ),
    }, "matched"


def dedupe_alphabet(events):
    # GOOG and GOOGL represent the same Alphabet earnings event.
    result = []
    seen_alphabet = set()

    for event in sorted(events, key=lambda e: e["reveal_at"]):
        if event["symbol"] in ("GOOG", "GOOGL"):
            key = (event["period"], event["release_date"])
            if key in seen_alphabet:
                continue
            seen_alphabet.add(key)
            event = dict(event)
            event["symbol"] = "ALPHABET"
        result.append(event)

    return result


async def main():
    if not POLYGON_CACHE.exists():
        raise SystemExit(f"Missing cache: {POLYGON_CACHE}")

    hub = ProviderHub()
    polygon = load_polygon()
    surprises = await fetch_surprises(hub)

    matched = []
    unmatched = []

    for symbol in SYMBOLS:
        for surprise in surprises.get(symbol, []):
            event, reason = choose_strict(symbol, surprise, polygon.get(symbol, []))
            if event:
                matched.append(event)
            else:
                unmatched.append({
                    "symbol": symbol,
                    "period": surprise.get("period"),
                    "quarter": surprise.get("quarter"),
                    "actual": surprise.get("actual"),
                    "estimate": surprise.get("estimate"),
                    "reason": reason,
                })

    matched = dedupe_alphabet(matched)
    matched.sort(key=lambda e: e["reveal_at"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # A6: sealed-artifact guard. This output is registered canonical
    # evidence, so a default run writes to a per-run directory instead.
    guarded_output_path(OUT_PATH).write_text(
        json.dumps(
            {
                "method": (
                    "STRICT: company identity + earnings-release language + "
                    "Finnhub actual EPS numeric confirmation in Polygon article. "
                    "No event is used before reveal_at."
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
        e for e in matched
        if "2026-07-01" <= e["release_date"] <= "2026-08-31"
    ]

    print("=== PHASE 19 STRICT EARNINGS MATCH ===")
    print("matched_2026 =", len(matched))
    print("unmatched_2026 =", len(unmatched))
    print("jul_aug_events =", len(jul_aug))
    print("cache =", OUT_PATH)
    print()

    print("=== JUL-AUG STRICT EVENTS ===")
    for e in jul_aug:
        print(
            e["release_date"],
            "|", e["symbol"],
            "| EPS", e["actual"], "vs", e["estimate"],
            "| surprise =", e["surprise_direction"],
            "| guidance =", e["guidance_direction"],
            "| reveal =", e["reveal_at"],
            "| score =", e["strict_match_score"],
            "| estimate_confirmed =", e["estimate_number_confirmed"],
        )
        print("   title =", str(e["release_title"])[:180])

    print()
    print("=== UNMATCHED COUNT BY REASON ===")
    counts = defaultdict(int)
    for u in unmatched:
        counts[u["reason"]] += 1
    for k, v in counts.items():
        print(k, "=", v)

    print()
    print("=== STRICT EARNINGS MATCH COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
