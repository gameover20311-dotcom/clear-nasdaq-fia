import asyncio
import csv
import httpx
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fia.providers import ProviderHub
from fia.artifact_guard import guarded_output_path
from fia_backtest_phase15.historical_news import filter_news_point_in_time
from fia_backtest_phase19.full_engine import build_forecast
from fia_backtest_phase19.earnings_pti import earnings_point_in_time, load_verified_events
from fia_backtest_phase19.full_snapshot import (
    SYMBOLS,
    clamp,
    hist1h,
    liquidity_asof,
    market_asof,
    normalize_article,
    normalize_timestamp,
    recency_asof,
    utc_ts,
)

START = datetime(2026, 7, 1, 17, 0, tzinfo=timezone.utc)
END = datetime(2026, 8, 31, 17, 0, tzinfo=timezone.utc)

OUTDIR = Path("fia_backtest_phase19/results")
CSV_PATH = OUTDIR / "phase19_full_backtest.csv"
JSON_PATH = OUTDIR / "phase19_full_backtest_summary.json"
POLYGON_CACHE_PATH = Path("fia_backtest_phase19/data/polygon_news_20260628_20260831.json")

NEUTRAL_THRESHOLD_PCT = 0.05
MAX_OUTCOME_STALENESS_MINUTES = 90


def direction_from_move(move_pct):
    if move_pct is None:
        return None
    if move_pct > NEUTRAL_THRESHOLD_PCT:
        return "BULLISH"
    if move_pct < -NEUTRAL_THRESHOLD_PCT:
        return "BEARISH"
    return "NEUTRAL"


def completed_nq_price(target):
    """Price known at target using only a fully completed 1h NQ bar.

    Yahoo intraday timestamps are bar starts, so a bar stamped 20:00
    represents 20:00-21:00. At 21:00 it is fully known.
    """
    df = hist1h("NQ=F")
    if df is None or df.empty:
        return None, None, None

    if df.index.tz is None:
        t = target.replace(tzinfo=None)
    else:
        t = target.astimezone(df.index.tz)

    cutoff = t - timedelta(hours=1)
    usable = df[df.index <= cutoff]
    if usable.empty:
        return None, None, None

    close = usable["Close"].dropna()
    if close.empty:
        return None, None, None

    bar_start = close.index[-1]
    bar_end = bar_start + timedelta(hours=1)
    staleness = t - bar_end

    if staleness > timedelta(minutes=MAX_OUTCOME_STALENESS_MINUTES):
        return None, bar_end, staleness.total_seconds() / 60.0

    return float(close.iloc[-1]), bar_end, max(0.0, staleness.total_seconds() / 60.0)



def normalize_polygon_article(article):
    if not isinstance(article, dict):
        return None
    title = str(article.get("title") or "").strip()
    if not title:
        return None
    publisher = article.get("publisher") or {}
    source = publisher.get("name") if isinstance(publisher, dict) else str(publisher or "Unknown")
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



def load_polygon_archive_cache():
    if not POLYGON_CACHE_PATH.exists():
        raise FileNotFoundError(
            f"Missing Polygon archive cache: {POLYGON_CACHE_PATH}. "
            "Run fia_backtest_phase19.polygon_archive_cache first."
        )

    payload = json.loads(POLYGON_CACHE_PATH.read_text(encoding="utf-8"))
    rows = payload.get("articles") or []

    if not isinstance(rows, list):
        raise RuntimeError("Polygon cache has invalid articles payload")

    return rows, {
        "status": "cached",
        "raw": len(rows),
        "path": str(POLYGON_CACHE_PATH),
        "start": payload.get("start"),
        "end": payload.get("end"),
        "windows": len(payload.get("windows") or []),
    }


async def prefetch_news_pool(hub, start, end):
    """Reproducible point-in-time historical news pool.

    Polygon market-wide news is loaded only from the completed local
    historical cache. Finnhub company news remains supplemental.
    No Polygon pagination or NewsAPI network calls occur during backtest.
    """
    pool = []
    source_counts = Counter()

    polygon_rows, polygon_meta = load_polygon_archive_cache()

    for article in polygon_rows:
        item = normalize_polygon_article(article)
        if item:
            pool.append(item)
            source_counts["Polygon_cached"] += 1

    fetch_start = (start - timedelta(days=3)).date().isoformat()
    fetch_end = end.date().isoformat()

    if hub.keys.get("FINNHUB_API_KEY"):
        async def one_symbol(symbol):
            payload = await hub.get(
                "https://finnhub.io/api/v1/company-news",
                {
                    "symbol": symbol,
                    "from": fetch_start,
                    "to": fetch_end,
                    "token": hub.keys["FINNHUB_API_KEY"],
                },
                timeout=30,
            )
            items = []
            for article in payload if isinstance(payload, list) else []:
                item = normalize_article(
                    article,
                    "Finnhub",
                    "company",
                    symbol,
                )
                if item:
                    items.append(item)
            return symbol, items

        responses = await asyncio.gather(
            *(one_symbol(symbol) for symbol in SYMBOLS),
            return_exceptions=True,
        )

        for result in responses:
            if isinstance(result, Exception):
                continue
            symbol, items = result
            pool.extend(items)
            source_counts[f"Finnhub:{symbol}"] += len(items)

    source_counts["Polygon_cache_rows"] = polygon_meta.get("raw", 0)
    source_counts["Polygon_cache_windows"] = polygon_meta.get("windows", 0)

    return pool, source_counts


async def prefetch_earnings_pool(hub, start, end):
    key = hub.keys.get("FINNHUB_API_KEY")
    if not key:
        return []

    payload = await hub.get(
        "https://finnhub.io/api/v1/calendar/earnings",
        {
            "from": (start.date() - timedelta(days=1)).isoformat(),
            "to": (end.date() + timedelta(days=7)).isoformat(),
            "token": key,
        },
        timeout=30,
    )

    return [
        event
        for event in (payload or {}).get("earningsCalendar", [])
        if event.get("symbol") in set(SYMBOLS)
    ]


def score_news_asof(target, hub, pool):
    articles = filter_news_point_in_time(pool, target.isoformat())

    # Preserve the same 3-day lookback used by Phase 19 full_snapshot.py.
    lower = target - timedelta(days=3)
    filtered = []
    for article in articles:
        try:
            published = normalize_timestamp(article.get("published_at"))
        except Exception:
            continue
        if published >= lower:
            filtered.append(article)
    articles = filtered

    if not articles:
        return {
            "news": None,
            "historical_news_evidence": "missing",
            "historical_news_articles": 0,
            "historical_news_clusters": 0,
            "historical_news_kept": 0,
            "historical_news_directional": 0,
        }

    enriched = []
    for article in articles:
        item = dict(article)
        try:
            item["fia_context"] = hub.analyze_news_context_v3_calibrated(item)
            item["fia_nasdaq_relevance"] = hub.analyze_nasdaq_relevance_v3(
                item,
                item["fia_context"],
            )
        except Exception:
            item["fia_context"] = {}
            item["fia_nasdaq_relevance"] = {}
        enriched.append(item)

    representatives = hub.detect_duplicate_news(enriched).get(
        "representatives",
        enriched,
    )
    quality = hub.filter_news_quality(representatives)

    original_recency = hub.calculate_news_recency_score
    hub.calculate_news_recency_score = lambda article: recency_asof(article, target)
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
        direction = str(context.get("direction", "neutral")).lower()

        if direction not in ("bullish", "bearish"):
            continue

        directional += 1
        sign = 1.0 if direction == "bullish" else -1.0

        direction_confidence = float(context.get("direction_confidence", 0) or 0)
        trust_score = float(trust.get("trust_score", 0) or 0)
        relevance = float(
            (article.get("fia_nasdaq_relevance", {}) or {}).get(
                "nasdaq_relevance_score",
                0,
            )
            or 0
        )
        context_confidence = float(
            (article.get("fia_context", {}) or {}).get(
                "primary_event_confidence",
                0,
            )
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

    return {
        "news": clamp(numerator / denominator) if denominator else 0.0,
        "historical_news_evidence": "available",
        "historical_news_articles": len(articles),
        "historical_news_clusters": len(representatives),
        "historical_news_kept": kept,
        "historical_news_directional": directional,
    }


def score_earnings_asof(target, hub, events):
    if not events:
        return {
            "earnings": None,
            "historical_earnings_evidence": "missing",
            "earnings_events": 0,
            "earnings_surprises_counted": 0,
        }

    ny = target.astimezone(hub.NY_TZ)
    relevant = []

    # Match Phase 19's one-day-back / seven-day-forward calendar window.
    min_date = target.date() - timedelta(days=1)
    max_date = target.date() + timedelta(days=7)

    for event in events:
        try:
            event_date = datetime.fromisoformat(str(event.get("date"))).date()
        except Exception:
            continue
        if min_date <= event_date <= max_date:
            relevant.append(event)

    pos = 0
    neg = 0
    counted = 0

    for event in relevant:
        try:
            event_date = datetime.fromisoformat(str(event.get("date"))).date()
        except Exception:
            continue

        done = event_date < ny.date()

        if event_date == ny.date():
            hour = str(event.get("hour") or "").lower()
            done = (
                (hour == "bmo" and ny.hour >= 10)
                or (hour == "amc" and ny.hour >= 18)
            )

        if not done:
            continue

        try:
            actual = float(event["epsActual"])
            estimate = float(event["epsEstimate"])
        except (TypeError, ValueError, KeyError):
            continue

        if actual > estimate:
            pos += 1
            counted += 1
        elif actual < estimate:
            neg += 1
            counted += 1

    score = clamp((pos - neg) / counted) if counted else (0.0 if relevant else None)

    return {
        "earnings": score,
        "historical_earnings_evidence": "available" if relevant else "missing",
        "earnings_events": len(relevant),
        "earnings_surprises_counted": counted,
        "earnings_positive": pos,
        "earnings_negative": neg,
    }


async def build_snapshot_cached(target, hub, news_pool):
    market = await asyncio.to_thread(market_asof, target)
    liquidity = await asyncio.to_thread(liquidity_asof, target, hub)

    news = score_news_asof(target, hub, news_pool)
    earnings = earnings_point_in_time(target)

    data = {
        **market,
        **liquidity,
        **news,
        **earnings,
    }
    data["macro"] = 0.0
    data["historical_macro_evidence"] = "live_parity_neutral"

    return {
        "status": "HISTORICAL_FULL",
        "timestamp": target.isoformat(),
        "data": data,
    }


def accuracy(rows, horizon):
    key = f"correct_{horizon}"
    resolved = [row for row in rows if row.get(key) is not None]
    if not resolved:
        return None, 0, 0
    correct = sum(bool(row[key]) for row in resolved)
    return correct / len(resolved) * 100.0, correct, len(resolved)


def brier_score(rows, horizon):
    actual_key = f"actual_{horizon}"
    vals = []

    for row in rows:
        actual = row.get(actual_key)
        if actual not in ("BULLISH", "BEARISH"):
            continue
        p = float(row["bullish_probability"]) / 100.0
        y = 1.0 if actual == "BULLISH" else 0.0
        vals.append((p - y) ** 2)

    return sum(vals) / len(vals) if vals else None, len(vals)


def print_direction_accuracy(rows, horizon):
    print(f"=== {horizon.upper()} DIRECTION ACCURACY ===")
    for direction in ("BULLISH", "BEARISH", "NEUTRAL"):
        subset = [
            row
            for row in rows
            if row["predicted"] == direction
            and row.get(f"correct_{horizon}") is not None
        ]
        if not subset:
            print(direction, "| n = 0")
            continue
        correct = sum(bool(row[f"correct_{horizon}"]) for row in subset)
        print(
            direction,
            "| n =", len(subset),
            "| accuracy =", round(correct / len(subset) * 100.0, 2), "%",
        )
    print()


def print_confidence(rows, horizon):
    print(f"=== {horizon.upper()} CONFIDENCE PERFORMANCE ===")
    for low, high in ((0, 50), (50, 60), (60, 70), (70, 101)):
        subset = [
            row
            for row in rows
            if low <= float(row["confidence"]) < high
            and row.get(f"correct_{horizon}") is not None
        ]
        if not subset:
            continue
        correct = sum(bool(row[f"correct_{horizon}"]) for row in subset)
        print(
            f"{low}-{high}% confidence",
            "| n =", len(subset),
            "| accuracy =", round(correct / len(subset) * 100.0, 2), "%",
        )
    print()


async def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)

    timestamps = []
    current = START
    while current <= END:
        if current.weekday() < 5:
            timestamps.append(current)
        current += timedelta(days=1)

    hub = ProviderHub()

    print("=== FIA PHASE 19 FULL BACKTEST ===")
    print("checkpoints =", len(timestamps))
    print("neutral threshold =", NEUTRAL_THRESHOLD_PCT, "%")
    print("outcome max staleness =", MAX_OUTCOME_STALENESS_MINUTES, "minutes")
    print()

    print("Loading cached Polygon history + supplemental Finnhub news...")
    news_pool, news_sources = await prefetch_news_pool(hub, START, END)
    print("news pool =", len(news_pool))
    print(
        "news sources =",
        dict(news_sources),
    )
    print()

    verified_earnings_events = load_verified_events()
    print("SEC-verified earnings cache events =", len(verified_earnings_events))
    print()

    rows = []
    liquidity_resolutions = Counter()
    news_evidence_counts = Counter()
    earnings_evidence_counts = Counter()
    earnings_catalyst_days = 0
    regime_counts = Counter()
    prediction_counts = Counter()

    for index, target in enumerate(timestamps, 1):
        try:
            snapshot = await build_snapshot_cached(
                target,
                hub,
                news_pool,
            )
            forecast = build_forecast(snapshot)
            data = snapshot["data"]

            entry = data.get("nq_futures_price")
            p4, bar4, stale4 = completed_nq_price(target + timedelta(hours=4))
            p8, bar8, stale8 = completed_nq_price(target + timedelta(hours=8))

            move4 = (
                ((p4 - float(entry)) / float(entry)) * 100.0
                if entry is not None and p4 is not None and float(entry) != 0
                else None
            )
            move8 = (
                ((p8 - float(entry)) / float(entry)) * 100.0
                if entry is not None and p8 is not None and float(entry) != 0
                else None
            )

            actual4 = direction_from_move(move4)
            actual8 = direction_from_move(move8)

            correct4 = (
                forecast.direction == actual4
                if actual4 is not None
                else None
            )
            correct8 = (
                forecast.direction == actual8
                if actual8 is not None
                else None
            )

            row = {
                "timestamp": target.isoformat(),
                "predicted": forecast.direction,
                "bullish_probability": forecast.bullish_probability,
                "bearish_probability": forecast.bearish_probability,
                "confidence": forecast.confidence,
                "score": forecast.score,
                "regime": forecast.regime,
                "data_coverage": forecast.data_coverage,
                "intelligence_coverage": forecast.intelligence_coverage,
                "entry_nq": entry,
                "nq_4h": p4,
                "nq_8h": p8,
                "move_4h_pct": move4,
                "move_8h_pct": move8,
                "actual_4h": actual4,
                "actual_8h": actual8,
                "correct_4h": correct4,
                "correct_8h": correct8,
                "outcome_4h_bar_end": str(bar4) if bar4 is not None else "",
                "outcome_8h_bar_end": str(bar8) if bar8 is not None else "",
                "outcome_4h_staleness_min": stale4,
                "outcome_8h_staleness_min": stale8,
                "news": data.get("news"),
                "news_articles": data.get("historical_news_articles"),
                "news_kept": data.get("historical_news_kept"),
                "news_directional": data.get("historical_news_directional"),
                "news_evidence": data.get("historical_news_evidence"),
                "news_polygon_articles": sum(1 for a in filter_news_point_in_time(news_pool, target.isoformat()) if a.get("provider") == "Polygon" and normalize_timestamp(a.get("published_at")) >= target - timedelta(days=3)),
                "news_finnhub_articles": sum(1 for a in filter_news_point_in_time(news_pool, target.isoformat()) if a.get("provider") == "Finnhub" and normalize_timestamp(a.get("published_at")) >= target - timedelta(days=3)),
                "liquidity_signal": data.get("liquidity_signal"),
                "liquidity_direction": data.get("liquidity_direction"),
                "liquidity_conflict": data.get("liquidity_conflict"),
                "liquidity_resolution": data.get("liquidity_resolution"),
                "liquidity_evidence": data.get("nq_liquidity_evidence"),
                "earnings": data.get("earnings"),
                "earnings_evidence": data.get("historical_earnings_evidence"),
                "earnings_released_events": data.get("earnings_released_events"),
                "earnings_released_symbols": ",".join(data.get("earnings_released_symbols") or []),
                "earnings_upcoming_events": data.get("earnings_upcoming_events"),
                "earnings_upcoming_symbols": ",".join(data.get("earnings_upcoming_symbols") or []),
                "earnings_upcoming_within_4h": data.get("earnings_upcoming_within_4h"),
                "earnings_upcoming_within_8h": data.get("earnings_upcoming_within_8h"),
                "earnings_upcoming_mega_weight": data.get("earnings_upcoming_mega_weight"),
                "earnings_upcoming_semi_count": data.get("earnings_upcoming_semi_count"),
                "earnings_hours_to_next": data.get("earnings_hours_to_next"),
                "earnings_catalyst_risk": data.get("earnings_catalyst_risk"),
                "earnings_future_eps_used": data.get("earnings_future_eps_used"),
                "market_available": data.get("provider_quotes_available"),
                "market_requested": data.get("provider_quotes_requested"),
            }
            rows.append(row)

            liquidity_resolutions[str(data.get("liquidity_resolution"))] += 1
            news_evidence_counts[str(data.get("historical_news_evidence"))] += 1
            earnings_evidence_counts[str(data.get("historical_earnings_evidence"))] += 1
            if data.get("earnings_catalyst_risk"):
                earnings_catalyst_days += 1
            regime_counts[forecast.regime] += 1
            prediction_counts[forecast.direction] += 1

            print(
                f"[{index:02d}/{len(timestamps)}]",
                target.date(),
                "| FIA", forecast.direction,
                "| P(bull)", forecast.bullish_probability,
                "| conf", forecast.confidence,
                "| news", round(float(data.get("news") or 0), 3),
                "| liq", data.get("liquidity_direction"),
                "| earnRisk", "YES" if data.get("earnings_catalyst_risk") else "NO",
                "| 4H", actual4 or "MISSING",
                "| 8H", actual8 or "MISSING",
            )

        except Exception as exc:
            print(
                f"[{index:02d}/{len(timestamps)}]",
                target.isoformat(),
                "| ERROR =", repr(exc),
            )

    if rows:
        fieldnames = list(rows[0].keys())
        # A6: sealed-artifact guard. The canonical result is evidence, so a
        # default run writes to a non-canonical per-run directory instead.
        csv_target = guarded_output_path(CSV_PATH)
        with csv_target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    acc4, correct4, resolved4 = accuracy(rows, "4h")
    acc8, correct8, resolved8 = accuracy(rows, "8h")

    brier4, brier4_n = brier_score(rows, "4h")
    brier8, brier8_n = brier_score(rows, "8h")

    summary = {
        "checkpoints_requested": len(timestamps),
        "forecasts_created": len(rows),
        "neutral_threshold_pct": NEUTRAL_THRESHOLD_PCT,
        "outcome_max_staleness_minutes": MAX_OUTCOME_STALENESS_MINUTES,
        "resolved_4h": resolved4,
        "correct_4h": correct4,
        "accuracy_4h_pct": acc4,
        "resolved_8h": resolved8,
        "correct_8h": correct8,
        "accuracy_8h_pct": acc8,
        "brier_4h": brier4,
        "brier_4h_n": brier4_n,
        "brier_8h": brier8,
        "brier_8h_n": brier8_n,
        "predictions": dict(prediction_counts),
        "regimes": dict(regime_counts),
        "liquidity_resolutions": dict(liquidity_resolutions),
        "news_evidence": dict(news_evidence_counts),
        "earnings_evidence": dict(earnings_evidence_counts),
        "earnings_catalyst_days": earnings_catalyst_days,
        "verified_earnings_cache_events": len(verified_earnings_events),
        "news_pool_size": len(news_pool),
        "polygon_cache_path": str(POLYGON_CACHE_PATH),
        "polygon_cache_exists": POLYGON_CACHE_PATH.exists(),
        "csv_path": str(csv_target) if rows else str(CSV_PATH),
    }

    json_target = guarded_output_path(JSON_PATH)
    json_target.write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )

    print()
    print("=== PHASE 19 OUTCOME SUMMARY ===")
    print("forecasts =", len(rows))
    print("4H resolved =", resolved4)
    print(
        "4H accuracy =",
        "N/A" if acc4 is None else f"{acc4:.2f} %",
    )
    print("8H resolved =", resolved8)
    print(
        "8H accuracy =",
        "N/A" if acc8 is None else f"{acc8:.2f} %",
    )
    print()

    print("=== PREDICTIONS ===")
    for key in ("BULLISH", "BEARISH", "NEUTRAL"):
        print(key, "=", prediction_counts.get(key, 0))
    print()

    print_direction_accuracy(rows, "4h")
    print_direction_accuracy(rows, "8h")
    print_confidence(rows, "4h")
    print_confidence(rows, "8h")

    print("=== PROBABILITY CALIBRATION ===")
    print(
        "4H Brier =",
        "N/A" if brier4 is None else round(brier4, 4),
        "| directional outcomes n =", brier4_n,
    )
    print(
        "8H Brier =",
        "N/A" if brier8 is None else round(brier8, 4),
        "| directional outcomes n =", brier8_n,
    )
    print()

    print("=== DATA QUALITY ===")
    print("liquidity resolutions =", dict(liquidity_resolutions))
    print("news evidence =", dict(news_evidence_counts))
    print("earnings evidence =", dict(earnings_evidence_counts))
    print("earnings catalyst days =", earnings_catalyst_days)
    print("verified earnings cache events =", len(verified_earnings_events))
    print("news pool =", len(news_pool))
    print("polygon cache =", POLYGON_CACHE_PATH)
    print()

    print("CSV =", csv_target if rows else CSV_PATH)
    print("SUMMARY =", json_target)
    print("=== FIA PHASE 19 FULL BACKTEST COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
