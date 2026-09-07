import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

from fia.providers import ProviderHub
from fia_backtest_phase15.historical_news import normalize_timestamp, filter_news_point_in_time

load_dotenv()


def clamp(value, low=-1.0, high=1.0):
    return max(low, min(high, float(value)))


def utc_ts(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def recency_asof(article, target):
    try:
        published = normalize_timestamp(article.get("published_at"))
    except Exception:
        return 0.50

    hours = max(0.0, (target - published).total_seconds() / 3600.0)
    for limit, score in [
        (1, 1.00),
        (3, 0.95),
        (6, 0.90),
        (12, 0.82),
        (24, 0.72),
        (48, 0.55),
        (72, 0.40),
        (120, 0.25),
    ]:
        if hours <= limit:
            return score
    return 0.15


def normalize_polygon_article(article):
    if not isinstance(article, dict):
        return None

    title = str(article.get("title") or "").strip()
    if not title:
        return None

    publisher = article.get("publisher") or {}
    source = (
        publisher.get("name")
        if isinstance(publisher, dict)
        else str(publisher or "Unknown")
    )

    description = str(article.get("description") or "").strip()

    return {
        "headline": title,
        "description": description,
        "summary": description,
        "source": source or "Unknown",
        "url": article.get("article_url") or "",
        "published_at": article.get("published_utc"),
        "provider": "Polygon",
        "category": "market",
        "symbol": None,
        "tickers": article.get("tickers") or [],
        "raw": article,
    }


async def fetch_polygon_news(target):
    key = os.getenv("POLYGON_API_KEY", "").strip()

    if not key:
        return [], "MISSING_KEY", 0

    start = target - timedelta(days=3)

    base_url = "https://api.polygon.io/v2/reference/news"
    params = {
        "published_utc.gte": start.isoformat(),
        "published_utc.lte": target.isoformat(),
        "order": "asc",
        "sort": "published_utc",
        "limit": 1000,
        "apiKey": key,
    }

    all_results = []
    pages = 0
    url = base_url
    next_params = params

    async with httpx.AsyncClient(timeout=30) as client:
        while url and pages < 5:
            try:
                response = await client.get(url, params=next_params)
            except Exception as exc:
                return all_results, f"NETWORK_ERROR:{type(exc).__name__}", pages

            if response.status_code != 200:
                return all_results, f"HTTP_{response.status_code}", pages

            try:
                payload = response.json()
            except Exception:
                return all_results, "BAD_JSON", pages

            results = payload.get("results") or []
            if isinstance(results, list):
                all_results.extend(results)

            pages += 1
            next_url = payload.get("next_url")

            if not next_url:
                break

            url = next_url
            next_params = {"apiKey": key}

    return all_results, "OK", pages


def score_articles_asof(articles, target, hub):
    normalized = []

    for article in articles:
        item = normalize_polygon_article(article)
        if item:
            normalized.append(item)

    normalized = filter_news_point_in_time(
        normalized,
        target.isoformat(),
    )

    if not normalized:
        return {
            "score": None,
            "articles": 0,
            "clusters": 0,
            "kept": 0,
            "directional": 0,
        }

    enriched = []

    for article in normalized:
        item = dict(article)

        try:
            item["fia_context"] = (
                hub.analyze_news_context_v3_calibrated(item)
            )
            item["fia_nasdaq_relevance"] = (
                hub.analyze_nasdaq_relevance_v3(
                    item,
                    item["fia_context"],
                )
            )
        except Exception:
            item["fia_context"] = {}
            item["fia_nasdaq_relevance"] = {}

        enriched.append(item)

    duplicate_result = hub.detect_duplicate_news(enriched)
    representatives = duplicate_result.get(
        "representatives",
        enriched,
    )

    quality = hub.filter_news_quality(representatives)

    original_recency = hub.calculate_news_recency_score
    hub.calculate_news_recency_score = (
        lambda article: recency_asof(article, target)
    )

    try:
        trusted = hub.apply_news_trust_scores(quality)
    finally:
        hub.calculate_news_recency_score = original_recency

    numerator = 0.0
    denominator = 0.0
    kept = 0
    directional = 0

    for article in trusted:
        trust = article.get("fia_news_trust", {}) or {}

        if str(trust.get("decision", "")).upper() == "REJECT":
            continue

        kept += 1

        context = hub.analyze_news_context(article)
        direction = str(
            context.get("direction", "neutral")
        ).lower()

        if direction not in ("bullish", "bearish"):
            continue

        directional += 1
        sign = 1.0 if direction == "bullish" else -1.0

        direction_confidence = float(
            context.get("direction_confidence", 0) or 0
        )

        trust_score = float(
            trust.get("trust_score", 0) or 0
        )

        relevance = float(
            (
                article.get("fia_nasdaq_relevance", {})
                or {}
            ).get("nasdaq_relevance_score", 0)
            or 0
        )

        context_confidence = float(
            (
                article.get("fia_context", {})
                or {}
            ).get("primary_event_confidence", 0)
            or 0
        )

        weight = max(
            0.05,
            trust_score
            * max(0.10, relevance)
            * max(0.25, context_confidence),
        )

        numerator += sign * direction_confidence * weight
        denominator += weight

    score = (
        clamp(numerator / denominator)
        if denominator
        else 0.0
    )

    return {
        "score": score,
        "articles": len(normalized),
        "clusters": len(representatives),
        "kept": kept,
        "directional": directional,
    }


async def main():
    target = utc_ts(
        sys.argv[1]
        if len(sys.argv) > 1
        else "2026-08-31T17:00:00+00:00"
    )

    hub = ProviderHub()

    raw, status, pages = await fetch_polygon_news(target)
    scored = score_articles_asof(raw, target, hub)

    print("=== PHASE 19 POLYGON HISTORICAL NEWS PROBE ===")
    print("timestamp =", target.isoformat())
    print("provider_status =", status)
    print("pages =", pages)
    print("raw_articles =", len(raw))
    print("point_in_time_articles =", scored["articles"])
    print("clusters =", scored["clusters"])
    print("kept =", scored["kept"])
    print("directional =", scored["directional"])
    print("news_score =", scored["score"])

    relevant = []
    for article in raw:
        tickers = article.get("tickers") or []
        if any(
            ticker in {
                "QQQ", "NVDA", "MSFT", "AAPL", "AMZN",
                "META", "AVGO", "GOOGL", "GOOG", "TSLA",
                "NFLX", "AMD", "MU", "INTC", "QCOM", "SMCI",
            }
            for ticker in tickers
        ):
            relevant.append(article)

    print("tracked_ticker_articles =", len(relevant))
    print("=== POLYGON NEWS PROBE COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
