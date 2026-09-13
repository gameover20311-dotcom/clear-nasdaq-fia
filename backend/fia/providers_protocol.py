# PHASE23_DATA_RELIABILITY_V1
# PHASE22_TRUTH_CONSISTENCY_V1
import yfinance as yf
import os
import time
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

load_dotenv()

"""CLEAR NASDAQ — providers.py split, PROTOCOL half.

PROTOCOL — what is admitted as evidence and how it is evaluated.

Source eligibility, fallback selection, staleness and freshness rules,
instrument/session windows, provider health and snapshot assembly. A change
here changes WHICH observations count, not what the model computes.

SPLIT MECHANICS
This module holds method bodies moved VERBATIM out of providers.py. It is a
mixin, not a standalone class: ProviderHub composes all three, so every
self.<method> call resolves exactly as it did before and the public
ProviderHub API is unchanged. Nothing here was rewritten, reordered inside a
method, or retyped; the split is a move.
"""


class ProtocolMixin:
    @staticmethod
    def _latest_candle_start(payload):
        if not isinstance(payload, dict):
            return None
        vals = []
        for x in payload.get("t") or []:
            try:
                vals.append(int(x))
            except (TypeError, ValueError, OverflowError):
                pass
        return max(vals) if vals else None
    async def finnhub_candles(
        self,
        symbol: str,
        resolution: str,
        start_ts: int,
        end_ts: int,
    ):
        """Return the freshest real candle series from the configured live paths.

        Finnhub remains primary when it succeeds. If it fails, Polygon and
        keyless Yahoo Chart are both evaluated and the series with the newest
        provider bar-start timestamp wins. Downstream completed-bar logic still
        rejects any forming row, so freshness cannot create future-bar leakage.
        """
        key = self.keys["FINNHUB_API_KEY"]

        if key:
            candles = await self.get(
                "https://" + "finnhub.io/api/v1/stock/candle",
                {
                    "symbol": symbol,
                    "resolution": resolution,
                    "from": start_ts,
                    "to": end_ts,
                    "token": key,
                },
                timeout=15,
            )
            if isinstance(candles, dict) and candles.get("s") == "ok":
                candles.setdefault("_fia_candle_source", "finnhub")
                self._candle_failure = None
                return candles
            print(f"Finnhub candles unavailable for {symbol} ({resolution}); trying fallbacks.")
            self._candle_failure = {
                "stage": "finnhub", "symbol": symbol, "resolution": str(resolution),
                "reason": "FINNHUB_CANDLES_UNAVAILABLE",
            }

        polygon_payload = None
        polygon_failure = None
        polygon_key = self.keys["POLYGON_API_KEY"]
        if polygon_key:
            resolution_map = {
                "D": ("1", "day"),
                "5": ("5", "minute"), "5m": ("5", "minute"),
                "15": ("15", "minute"), "15m": ("15", "minute"),
                "30": ("30", "minute"), "30m": ("30", "minute"),
                "60": ("60", "minute"), "60m": ("60", "minute"),
            }
            multiplier, timespan = resolution_map.get(str(resolution), ("1", "day"))
            start_date = datetime.utcfromtimestamp(int(start_ts)).strftime("%Y-%m-%d")
            end_date = datetime.utcfromtimestamp(int(end_ts)).strftime("%Y-%m-%d")
            polygon_url = (
                f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/"
                f"{multiplier}/{timespan}/{start_date}/{end_date}"
            )
            polygon = await self.get(
                polygon_url,
                {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": polygon_key},
                timeout=15,
            )
            if not isinstance(polygon, dict):
                polygon_failure = {
                    "stage": "polygon", "symbol": symbol, "resolution": str(resolution),
                    "reason": "POLYGON_REQUEST_FAILED",
                    "remediation": "Polygon returned no usable response (auth, rate limit or network).",
                }
            results = (polygon.get("results") or []) if isinstance(polygon, dict) else []
            if results:
                timestamps, highs, lows, closes, opens, volumes = [], [], [], [], [], []
                for row in results:
                    try:
                        ts_ms = row.get("t")
                        high = row.get("h")
                        low = row.get("l")
                        close = row.get("c")
                        open_ = row.get("o")
                        if ts_ms is None or high is None or low is None or close is None:
                            continue
                        timestamps.append(int(ts_ms) // 1000)
                        highs.append(float(high))
                        lows.append(float(low))
                        closes.append(float(close))
                        opens.append(float(open_) if open_ is not None else float(close))
                        try:
                            volumes.append(float(row.get("v") or 0.0))
                        except (TypeError, ValueError):
                            volumes.append(0.0)
                    except (TypeError, ValueError, OverflowError, AttributeError):
                        continue
                if timestamps:
                    polygon_payload = {
                        "s": "ok", "t": timestamps, "h": highs, "l": lows,
                        "c": closes, "o": opens, "v": volumes,
                        "_fia_candle_source": "polygon_fallback",
                    }
                    print(f"Polygon fallback available for {symbol} ({resolution}): {len(timestamps)} candles.")
            if polygon_payload is None:
                if polygon_failure is None:
                    polygon_failure = {
                        "stage": "polygon", "symbol": symbol, "resolution": str(resolution),
                        "reason": "POLYGON_EMPTY_RESULTS",
                        "remediation": "Polygon returned no aggregate rows usable as candles.",
                    }
                print(f"Polygon fallback returned no usable candles for {symbol} ({resolution}).")
        else:
            polygon_failure = {
                "stage": "polygon", "symbol": symbol, "resolution": str(resolution),
                "reason": "POLYGON_API_KEY_NOT_CONFIGURED",
                "remediation": "Set POLYGON_API_KEY in the deployment environment.",
            }
            print("Polygon fallback unavailable: POLYGON_API_KEY is missing.")

        yahoo_payload = await self._yahoo_chart_candles(symbol, resolution, start_ts, end_ts)
        if isinstance(yahoo_payload, dict):
            print(f"Yahoo chart fallback available for {symbol} ({resolution}): {len(yahoo_payload.get('t') or [])} candles.")

        p_latest = self._latest_candle_start(polygon_payload)
        y_latest = self._latest_candle_start(yahoo_payload)
        chosen = None
        if y_latest is not None and (p_latest is None or y_latest > p_latest):
            chosen = yahoo_payload
        elif p_latest is not None:
            chosen = polygon_payload
        elif y_latest is not None:
            chosen = yahoo_payload

        if isinstance(chosen, dict):
            self._candle_failure = None
            print(
                f"Candle fallback selected for {symbol} ({resolution}): "
                f"{chosen.get('_fia_candle_source')} latest_start={self._latest_candle_start(chosen)}"
            )
            return chosen

        # Preserve the most actionable provider-specific diagnostic. Yahoo is a
        # keyless rescue path; its failure must not erase whether Polygon was
        # unconfigured, rejected/rate-limited, or simply returned no rows.
        self._candle_failure = polygon_failure or {
            "stage": "fallbacks", "symbol": symbol, "resolution": str(resolution),
            "reason": "NO_USABLE_CANDLE_PROVIDER",
            "remediation": "Finnhub, Polygon and Yahoo Chart returned no usable candle series.",
        }
        if isinstance(self._candle_failure, dict):
            self._candle_failure["yahoo_fallback_attempted"] = True
        return None
    @staticmethod
    def _normalize_live_news_article(article, provider):
        if not isinstance(article, dict):
            return None
        title = str(article.get("title") or article.get("headline") or "").strip()
        if not title:
            return None
        description = str(article.get("description") or article.get("summary") or "").strip()
        published = article.get("publishedAt")
        if published is None:
            published = article.get("published_at")
        if published is None:
            published = article.get("datetime")
        return {
            "title": title,
            "description": description,
            "publishedAt": published,
            "_fia_news_provider": provider,
        }
    @staticmethod
    def _news_article_age_seconds(article, now_utc=None):
        now_utc = now_utc or datetime.now(timezone.utc)
        ts = (article or {}).get("publishedAt")
        if ts is None:
            ts = (article or {}).get("published_at")
        if ts is None:
            ts = (article or {}).get("datetime")
        if ts is None:
            return None
        try:
            if isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            else:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
            return float((now_utc - dt).total_seconds())
        except (TypeError, ValueError, OSError, OverflowError):
            return None
    async def live_news_articles(self, stale_ceiling_seconds: float = 43200.0):
        """Choose the freshest truthful live-news provider packet.

        NewsAPI remains primary while its newest article is within the existing
        12-hour ceiling. Only when it is empty/untimestamped/stale do we request
        Finnhub market news. A future-dated row (>60s clock tolerance) is rejected
        rather than allowed to make a provider look artificially fresh.
        """
        now_mono = time.time()
        if (self._live_news_cache is not None and
                now_mono - self._live_news_cache_time < self.LIVE_NEWS_CACHE_SECONDS):
            return dict(self._live_news_cache)

        now_utc = datetime.now(timezone.utc)

        def clean(rows, provider):
            out = []
            for raw in rows or []:
                item = self._normalize_live_news_article(raw, provider)
                if not item:
                    continue
                age = self._news_article_age_seconds(item, now_utc)
                if age is not None and age < -60.0:
                    continue
                out.append(item)
            return out

        def newest_age(rows):
            ages = [self._news_article_age_seconds(x, now_utc) for x in rows]
            ages = [x for x in ages if x is not None and x >= -60.0]
            return min(ages) if ages else None

        newsapi_rows = []
        if self.keys.get("NEWS_API_KEY"):
            try:
                payload = await self.news_sentiment("QQQ")
                newsapi_rows = clean((payload or {}).get("articles") if isinstance(payload, dict) else [], "NewsAPI")
            except Exception as exc:
                print(f"NewsAPI live-news selection error -> {type(exc).__name__}")

        n_age = newest_age(newsapi_rows)
        selected = newsapi_rows
        selected_provider = "NewsAPI" if newsapi_rows else None
        finnhub_rows = []
        f_age = None

        if not newsapi_rows or n_age is None or n_age > float(stale_ceiling_seconds):
            try:
                finnhub_rows = clean(await self.finnhub_market_news(), "Finnhub")
                f_age = newest_age(finnhub_rows)
            except Exception as exc:
                print(f"Finnhub live-news selection error -> {type(exc).__name__}")

            # Prefer Finnhub only when it has a valid timestamped packet fresher
            # than NewsAPI. Missing timestamp is not evidence of freshness.
            if finnhub_rows and f_age is not None and (n_age is None or f_age < n_age):
                selected = finnhub_rows
                selected_provider = "Finnhub"

        result = {
            "articles": selected,
            "selected_provider": selected_provider,
            "newest_age_seconds": newest_age(selected),
            "candidate_counts": {"NewsAPI": len(newsapi_rows), "Finnhub": len(finnhub_rows)},
            "candidate_newest_age_seconds": {"NewsAPI": n_age, "Finnhub": f_age},
            "stale_ceiling_seconds": float(stale_ceiling_seconds),
        }
        self._live_news_cache = dict(result)
        self._live_news_cache_time = time.time()
        return result
    async def unified_news_feed(
        self,
        company_symbols=None,
        company_days: int = 7,
        market_limit: int = 100,
        company_limit: int = 50,
    ):
        """
        Collects raw news from all available providers and converts
        everything into one standard FIA news format.

        IMPORTANT:
        This function does NOT score or trust the news yet.
        Quality filtering and intelligence happen in later layers.
        """

        if company_symbols is None:
            company_symbols = [
                "NVDA",
                "MSFT",
                "AAPL",
                "AMZN",
                "META",
                "AVGO",
                "GOOGL",
                "TSLA",
                "AMD",
                "NFLX",
            ]

        unified = []

        def normalize(article, provider, category, symbol=None):
            if not isinstance(article, dict):
                return None

            headline = (
                article.get("headline")
                or article.get("title")
                or ""
            ).strip()

            description = (
                article.get("summary")
                or article.get("description")
                or ""
            ).strip()

            if not headline:
                return None

            published = (
                article.get("datetime")
                or article.get("publishedAt")
                or article.get("published_at")
            )

            return {
                "headline": headline,
                "description": description,
                "source": (
                    article.get("source", {}).get("name")
                    if isinstance(article.get("source"), dict)
                    else (
                        article.get("source")
                        or article.get("author")
                        or "Unknown"
                    )
                ),
                "url": (
                    article.get("url")
                    or ""
                ),
                "published_at": published,
                "provider": provider,
                "category": category,
                "symbol": symbol,
                "raw": article,
            }

        # -----------------------------------------------------
        # NewsAPI
        # -----------------------------------------------------

        try:
            newsapi = await self.news_sentiment("QQQ")

            if newsapi and newsapi.get("articles"):

                for article in newsapi.get("articles", []):

                    item = normalize(
                        article,
                        provider="NewsAPI",
                        category="market",
                    )

                    if item:
                        unified.append(item)

        except Exception as e:
            print(f"Unified NewsAPI error -> {e}")

        # -----------------------------------------------------
        # Finnhub Market News
        # -----------------------------------------------------

        try:
            market_news = await self.finnhub_market_news()

            for article in market_news[:market_limit]:

                item = normalize(
                    article,
                    provider="Finnhub",
                    category="market",
                )

                if item:
                    unified.append(item)

        except Exception as e:
            print(f"Unified Finnhub market news error -> {e}")

        # -----------------------------------------------------
        # Finnhub Company News
        # -----------------------------------------------------

        for symbol in company_symbols:

            try:

                company_news = await self.finnhub_company_news(
                    symbol,
                    days=company_days,
                )

                for article in company_news[:company_limit]:

                    item = normalize(
                        article,
                        provider="Finnhub",
                        category="company",
                        symbol=symbol,
                    )

                    if item:
                        unified.append(item)

            except Exception as e:
                print(
                    f"Unified Finnhub company news error "
                    f"for {symbol} -> {e}"
                )

        # =====================================================
        # FIA NEWS CONTEXT INTELLIGENCE
        # =====================================================

        for item in unified:

            if isinstance(item, dict):

                item["fia_context"] = (
                    self.analyze_news_context_v3_calibrated(item)
                )

        # =====================================================
        # FIA DUPLICATE CLUSTERING + SOURCE CONFIRMATION
        # =====================================================

        duplicate_result = self.detect_duplicate_news(
            unified
        )

        unified = duplicate_result.get(
            "representatives",
            unified,
        )

        return unified
    def evaluate_news_quality(self, article):
        """
        First-stage FIA news intelligence.

        Evaluates one normalized news article and returns:
        quality_score, relevance_score, decision and reasons.

        IMPORTANT:
        This does not modify market forecasts yet.
        """

        if not isinstance(article, dict):
            return {
                "decision": "REJECT",
                "quality_score": 0.0,
                "relevance_score": 0.0,
                "reasons": ["Invalid article format"],
            }

        headline = str(article.get("headline", "")).lower()
        description = str(article.get("description", "")).lower()
        source = str(article.get("source", "")).lower()
        raw_symbol = article.get("symbol")
        symbol = (
            str(raw_symbol).upper().strip()
            if raw_symbol
            else ""
        )

        text = f"{headline} {description}"

        reasons = []

        # -------------------------------------------------
        # Source quality
        # -------------------------------------------------

        high_quality_sources = {
            "reuters",
            "cnbc",
            "bloomberg",
            "financial times",
            "wall street journal",
            "the wall street journal",
            "associated press",
            "marketwatch",
            "barron's",
            "barrons",
        }

        medium_quality_sources = {
            "yahoo finance",
            "24/7 wall st.",
            "benzinga",
            "investing.com",
            "the motley fool",
            "seeking alpha",
        }

        low_quality_sources = {
            "biztoc.com",
            "yahoo entertainment",
            "slashdot.org",
        }

        quality_score = 0.50

        if source in high_quality_sources:
            quality_score = 1.00
            reasons.append("High-quality primary financial source")

        elif source in medium_quality_sources:
            quality_score = 0.70
            reasons.append("Medium-quality financial source")

        elif source in low_quality_sources:
            quality_score = 0.20
            reasons.append("Low-quality or aggregator source")

        else:
            quality_score = 0.45
            reasons.append("Unknown source quality")

        # -------------------------------------------------
        # Noise / irrelevant content detection
        # -------------------------------------------------

        reject_keywords = [
            "inherited",
            "boyfriend",
            "dating",
            "celebrity",
            "entertainment",
            "lottery",
            "relationship",
            "wedding",
            "horoscope",
        ]

        crypto_keywords = [
            "bitcoin",
            "ethereum",
            "uniswap",
            "bnb chain",
            "crypto token",
            "tokenized stocks",
            "blockchain",
            "defi",
            "dex volume",
        ]

        if any(word in text for word in reject_keywords):
            return {
                "decision": "REJECT",
                "quality_score": quality_score,
                "relevance_score": 0.0,
                "reasons": reasons + [
                    "Personal, entertainment or non-market content"
                ],
            }

        # Crypto is not automatically useful for NASDAQ.
        # Keep only for review instead of blindly trusting it.

        crypto_detected = any(
            word in text for word in crypto_keywords
        )

        # -------------------------------------------------
        # NASDAQ relevance
        # -------------------------------------------------

        relevance_score = 0.0

        nasdaq_keywords = [
            "nasdaq",
            "qqq",
            "technology stocks",
            "tech stocks",
            "growth stocks",
        ]

        mega_cap_keywords = [
            "nvidia",
            "nvda",
            "microsoft",
            "msft",
            "apple",
            "aapl",
            "amazon",
            "amzn",
            "meta",
            "alphabet",
            "google",
            "googl",
            "broadcom",
            "avgo",
            "tesla",
            "tsla",
            "netflix",
            "nflx",
            "amd",
        ]

        macro_keywords = [
            "federal reserve",
            "fed",
            "interest rate",
            "rate hike",
            "rate cut",
            "inflation",
            "cpi",
            "jobs report",
            "payrolls",
            "treasury yield",
            "bond yields",
            "recession",
        ]

        earnings_keywords = [
            "earnings",
            "guidance",
            "revenue",
            "profit",
            "forecast",
            "beat estimates",
            "miss estimates",
        ]

        if any(word in text for word in nasdaq_keywords):
            relevance_score += 0.45
            reasons.append("Direct NASDAQ/technology relevance")

        if any(word in text for word in mega_cap_keywords):
            relevance_score += 0.40
            reasons.append("NASDAQ mega-cap relevance")

        if any(word in text for word in macro_keywords):
            relevance_score += 0.35
            reasons.append("Macro market relevance")

        if any(word in text for word in earnings_keywords):
            relevance_score += 0.20
            reasons.append("Earnings or financial relevance")

        if symbol:
            relevance_score += 0.15
            reasons.append(f"Tracked company symbol: {symbol}")

        relevance_score = min(1.0, relevance_score)

        # -------------------------------------------------
        # FIA CONTEXT INTELLIGENCE INTEGRATION
        # -------------------------------------------------

        context = article.get("fia_context")

        if not isinstance(context, dict):

            try:

                context = self.analyze_news_context(article)

            except Exception:

                context = {}

        context_event = str(
            context.get("event_type", "")
        ).lower()

        context_symbols = (
            context.get("affected_symbols") or []
        )

        context_sector = str(
            context.get("sector", "")
        ).lower()

        try:

            context_impact = float(
                context.get(
                    "impact_strength",
                    0.0,
                ) or 0.0
            )

        except Exception:

            context_impact = 0.0

        # Direct tracked-company relevance.

        if context_symbols:

            relevance_score += 0.20

            reasons.append(
                "Context Intelligence identified tracked symbol relevance"
            )

        # Major market-moving events.

        if context_event in {

            "earnings",

            "monetary_policy",

            "macroeconomic",

        }:

            relevance_score += 0.15

            reasons.append(
                "Context Intelligence confirmed market event: "
                + context_event
            )

        elif (

            context_event == "technology"

            and context_symbols

        ):

            relevance_score += 0.10

            reasons.append(
                "Context Intelligence confirmed tracked technology relevance"
            )

        # NASDAQ-sensitive sectors.

        if context_sector in {

            "semiconductors",

            "artificial_intelligence",

            "macro_rates",

        }:

            relevance_score += 0.10

            reasons.append(
                "Context Intelligence identified relevant sector: "
                + context_sector
            )

        # Higher expected market impact.

        if context_impact >= 0.50:

            relevance_score += 0.10

            reasons.append(
                "Context Intelligence identified elevated market impact"
            )

        relevance_score = min(
            1.0,
            relevance_score,
        )



        # -------------------------------------------------
        # FIA QUALITY CALIBRATION V1
        # -------------------------------------------------

        # Strong Context Intelligence confirmation can
        # upgrade high-value market news.

        context_confirmed = (
            bool(context_symbols)
            or context_event in {
                "earnings",
                "monetary_policy",
                "macroeconomic",
            }
        )

        strong_market_context = (
            context_confirmed
            and relevance_score >= 0.60
            and context_impact >= 0.40
        )

        high_confidence_technology = (
            context_event == "technology"
            and bool(context_symbols)
            and relevance_score >= 0.65
        )

        # -------------------------------------------------
        # Final decision
        # -------------------------------------------------

        if crypto_detected and relevance_score < 0.45:
            decision = "REJECT"
            reasons.append(
                "Crypto content without sufficient NASDAQ relevance"
            )

        elif (
            strong_market_context
            and quality_score >= 0.45
        ):
            decision = "KEEP"
            reasons.append(
                "Strong market relevance confirmed by Context Intelligence"
            )

        elif (
            high_confidence_technology
            and quality_score >= 0.45
        ):
            decision = "KEEP"
            reasons.append(
                "High-confidence tracked technology market relevance"
            )

        elif quality_score >= 0.70 and relevance_score >= 0.45:
            decision = "KEEP"
            reasons.append(
                "Strong source and meaningful market relevance"
            )

        elif relevance_score >= 0.25:
            decision = "REVIEW"
            reasons.append(
                "Potential relevance but requires deeper analysis"
            )

        else:
            decision = "REJECT"
            reasons.append(
                "Insufficient NASDAQ market relevance"
            )

        return {
            "decision": decision,
            "quality_score": round(quality_score, 2),
            "relevance_score": round(relevance_score, 2),
            "reasons": reasons,
        }
    def filter_news_quality(self, articles):
        """
        Evaluates a list of normalized news articles.

        Adds FIA quality intelligence without deleting raw data.
        """

        results = []

        for article in articles or []:

            evaluation = self.evaluate_news_quality(article)

            item = dict(article)

            item["fia_news_quality"] = evaluation

            results.append(item)

        return results
    def calculate_news_recency_score(self, article: dict) -> float:
        """
        Universal news timestamp parser.

        Supports:
        - Finnhub Unix timestamps
        - NewsAPI ISO timestamps
        - ISO strings with Z / timezone offsets

        Returns a score from 0.0 to 1.0.
        """

        from datetime import datetime, timezone

        timestamp = (
            article.get("datetime")
            or article.get("publishedAt")
            or article.get("published_at")
            or article.get("timestamp")
            or article.get("time")
        )

        # Safe fallback when no usable timestamp exists.
        if timestamp is None:
            return 0.50

        published = None

        try:
            # -------------------------------------------------
            # UNIX TIMESTAMP
            # -------------------------------------------------
            if isinstance(timestamp, (int, float)):

                value = float(timestamp)

                # Milliseconds timestamp protection.
                if value > 100000000000:
                    value /= 1000.0

                published = datetime.fromtimestamp(
                    value,
                    tz=timezone.utc,
                )

            # -------------------------------------------------
            # STRING TIMESTAMP
            # -------------------------------------------------
            elif isinstance(timestamp, str):

                value = timestamp.strip()

                if not value:
                    return 0.50

                # Numeric timestamp inside a string.
                try:
                    numeric_value = float(value)

                    if numeric_value > 100000000000:
                        numeric_value /= 1000.0

                    published = datetime.fromtimestamp(
                        numeric_value,
                        tz=timezone.utc,
                    )

                except ValueError:

                    # NewsAPI commonly uses trailing Z.
                    if value.endswith("Z"):
                        value = value[:-1] + "+00:00"

                    published = datetime.fromisoformat(
                        value
                    )

                    # Naive datetime protection.
                    if published.tzinfo is None:
                        published = published.replace(
                            tzinfo=timezone.utc
                        )

                    else:
                        published = published.astimezone(
                            timezone.utc
                        )

        except Exception:
            return 0.50

        if published is None:
            return 0.50

        try:
            age_hours = (
                datetime.now(timezone.utc) - published
            ).total_seconds() / 3600.0

        except Exception:
            return 0.50

        # Future timestamps can happen due to provider clock errors.
        if age_hours < 0:
            age_hours = 0

        # -----------------------------------------------------
        # RECENCY DECAY MODEL
        # -----------------------------------------------------

        if age_hours <= 1:
            return 1.00

        if age_hours <= 3:
            return 0.95

        if age_hours <= 6:
            return 0.90

        if age_hours <= 12:
            return 0.82

        if age_hours <= 24:
            return 0.72

        if age_hours <= 48:
            return 0.55

        if age_hours <= 72:
            return 0.40

        if age_hours <= 120:
            return 0.25

        return 0.15
    def calculate_news_trust_score(self, article: dict) -> dict:
        """
        Combines FIA News Quality and Market Relevance into a
        stronger final trust decision.

        Components:
        - Source quality
        - NASDAQ relevance
        - Recency
        - Market impact
        - Future multi-source confirmation compatibility
        """

        quality_data = article.get("fia_news_quality", {}) or {}

        quality = float(
            quality_data.get("quality_score", 0.0) or 0.0
        )

        relevance = float(
            quality_data.get("relevance_score", 0.0) or 0.0
        )

        headline = str(
            article.get("headline")
            or article.get("title")
            or ""
        ).lower()

        # -----------------------------------------------------
        # RECENCY
        # -----------------------------------------------------

        # Universal parser handles Finnhub Unix timestamps,
        # NewsAPI ISO timestamps, milliseconds and timezone data.
        recency = self.calculate_news_recency_score(
            article
        )

        # -----------------------------------------------------
        # MARKET IMPACT
        # -----------------------------------------------------

        high_impact_words = {
            "fed",
            "federal reserve",
            "interest rate",
            "rates",
            "cpi",
            "inflation",
            "jobs report",
            "payroll",
            "gdp",
            "recession",
            "tariff",
            "sanctions",
            "war",
            "oil",
            "yield",
            "earnings",
            "guidance",
            "forecast",
            "upgrade",
            "downgrade",
            "beat",
            "miss",
            "nvidia",
            "nvda",
            "apple",
            "aapl",
            "microsoft",
            "msft",
            "amazon",
            "amzn",
            "alphabet",
            "googl",
            "meta",
            "tesla",
            "tsla",
            "amd",
            "avgo",
        }

        impact_hits = sum(
            1
            for word in high_impact_words
            if word in headline
        )

        if impact_hits >= 3:
            market_impact = 1.00
        elif impact_hits == 2:
            market_impact = 0.80
        elif impact_hits == 1:
            market_impact = 0.60
        else:
            market_impact = 0.20

        # -----------------------------------------------------
        # MULTI-SOURCE CONFIRMATION
        #
        # Reserved for unified feed clustering.
        # Safe default until confirmation engine is connected.
        # -----------------------------------------------------

        # -----------------------------------------------------
        # MULTI-SOURCE CONFIRMATION
        # -----------------------------------------------------
        #
        # Uses duplicate clustering to determine how many
        # independent sources confirm the same story.
        #
        confirmation = (
            self.calculate_source_confirmation_score(
                article
            )
        )

        confirmation = max(
            0.0,
            min(1.0, float(confirmation)),
        )

        # -----------------------------------------------------
        # FINAL TRUST SCORE
        #
        # Source quality and NASDAQ relevance receive the
        # highest importance.
        # -----------------------------------------------------

        trust_score = (
            quality * 0.35
            + relevance * 0.35
            + recency * 0.15
            + market_impact * 0.10
            + confirmation * 0.05
        )

        trust_score = max(
            0.0,
            min(1.0, trust_score),
        )

        # -----------------------------------------------------
        # HARD SAFETY RULES
        # -----------------------------------------------------

        source_decision = str(
            quality_data.get("decision", "")
        ).upper()

        if quality < 0.30 and relevance < 0.50:
            decision = "REJECT"

        elif source_decision == "REJECT" and trust_score < 0.65:
            decision = "REJECT"

        elif trust_score >= 0.70:
            decision = "KEEP"

        elif trust_score >= 0.40:
            decision = "REVIEW"

        else:
            decision = "REJECT"

        return {
            "trust_score": round(
                trust_score,
                3,
            ),
            "source_quality": round(
                quality,
                3,
            ),
            "nasdaq_relevance": round(
                relevance,
                3,
            ),
            "recency_score": round(
                recency,
                3,
            ),
            "market_impact": round(
                market_impact,
                3,
            ),
            "source_confirmation": round(
                confirmation,
                3,
            ),
            "decision": decision,
        }
    def apply_news_trust_scores(
        self,
        articles,
    ):
        """
        Adds final FIA trust intelligence to each article.
        """

        results = []

        for article in articles or []:

            if not isinstance(article, dict):
                continue

            item = dict(article)

            item["fia_news_trust"] = (
                self.calculate_news_trust_score(item)
            )

            results.append(item)

        return results
    def _news_normalized_words(self, headline):
        """
        Creates a normalized set of meaningful headline words
        for duplicate and similar-news detection.
        """

        import re

        text = str(headline or "").lower()

        text = re.sub(
            r"[^a-z0-9\s]",
            " ",
            text,
        )

        stop_words = {
            "the", "a", "an", "and", "or", "of",
            "to", "in", "for", "on", "with",
            "from", "at", "by", "as", "is",
            "are", "was", "were", "after",
            "before", "says", "said",
        }

        words = {
            word
            for word in text.split()
            if len(word) >= 3
            and word not in stop_words
        }

        return words
    def news_headline_similarity(
        self,
        headline_a,
        headline_b,
    ):
        """
        Returns similarity from 0.0 to 1.0 using
        normalized headline word overlap.
        """

        words_a = self._news_normalized_words(
            headline_a
        )

        words_b = self._news_normalized_words(
            headline_b
        )

        if not words_a or not words_b:
            return 0.0

        intersection = len(
            words_a.intersection(words_b)
        )

        union = len(
            words_a.union(words_b)
        )

        if union == 0:
            return 0.0

        return intersection / union
    def detect_duplicate_news(
        self,
        articles,
        similarity_threshold=0.55,
    ):
        """
        Groups similar headlines into duplicate clusters.

        Returns:
        - representatives: one article per cluster
        - clusters: complete duplicate information
        """

        articles = (
            articles
            if isinstance(articles, list)
            else []
        )

        clusters = []

        for article in articles:

            if not isinstance(article, dict):
                continue

            headline = article.get(
                "headline"
            ) or article.get(
                "title"
            ) or ""

            if not headline:
                continue

            matched_cluster = None

            for cluster in clusters:

                similarity = (
                    self.news_headline_similarity(
                        headline,
                        cluster["headline"],
                    )
                )

                if similarity >= similarity_threshold:
                    matched_cluster = cluster
                    break

            if matched_cluster is None:

                clusters.append(
                    {
                        "headline": headline,
                        "articles": [article],
                    }
                )

            else:

                matched_cluster[
                    "articles"
                ].append(article)

        representatives = []
        cluster_results = []

        for cluster in clusters:

            cluster_articles = cluster[
                "articles"
            ]

            sources = set()

            for article in cluster_articles:

                source = article.get(
                    "source"
                )

                if isinstance(source, dict):
                    source = source.get(
                        "name"
                    ) or source.get("id")

                source = str(
                    source or ""
                ).strip()

                if source:
                    sources.add(source.lower())

            representative = dict(
                cluster_articles[0]
            )

            representative[
                "fia_duplicate_cluster_size"
            ] = len(cluster_articles)

            representative[
                "fia_confirming_sources"
            ] = sorted(sources)

            representative[
                "fia_source_confirmation_count"
            ] = len(sources)

            representatives.append(
                representative
            )

            cluster_results.append(
                {
                    "headline": cluster[
                        "headline"
                    ],
                    "articles": cluster_articles,
                    "source_count": len(sources),
                    "sources": sorted(sources),
                }
            )

        return {
            "representatives": representatives,
            "clusters": cluster_results,
        }
    def calculate_source_confirmation_score(
        self,
        article,
    ):
        """
        Converts independent-source confirmation into
        a score from 0.0 to 1.0.
        """

        count = article.get(
            "fia_source_confirmation_count",
            1,
        )

        try:
            count = int(count)
        except Exception:
            count = 1

        if count >= 5:
            return 1.00

        if count == 4:
            return 0.95

        if count == 3:
            return 0.85

        if count == 2:
            return 0.70

        return 0.50
    def current_nq_futures_symbol(self):
        """
        Returns active Nasdaq futures contract.
        H=Mar, M=Jun, U=Sep, Z=Dec.
        """

        now = self.now_ny()

        contracts = [
            (3, "H"),
            (6, "M"),
            (9, "U"),
            (12, "Z"),
        ]

        for month, code in contracts:
            if now.month < month:
                return f"NQ{code}{str(now.year)[-1]}"

        return f"NQH{str(now.year + 1)[-1]}"
    async def snapshot(self) -> Dict[str, Any]:
        """
        Main market snapshot.

        Returns:
          QQQ
          SPY
          mega-cap leadership
          semiconductors
          breadth
          FRED macro
          news
          earnings
          liquidity
        """

        # -----------------------------------------------------
        # Cache
        # -----------------------------------------------------

        now_ts = time.time()

        if (
            self._snapshot_cache is not None
            and now_ts - self._snapshot_cache_time
            < self.SNAPSHOT_CACHE_SECONDS
        ):
            return self._snapshot_cache

        finnhub_key = self.keys["FINNHUB_API_KEY"]

        if not finnhub_key:
            result = {
                "data": {},
                "status": "NO_FINNHUB_KEY",
                "provider": None,
                "timestamp": time.time(),
            }

            self._snapshot_cache = result
            self._snapshot_cache_time = time.time()

            return result

        # -----------------------------------------------------
        # Symbols
        # -----------------------------------------------------

        symbols = [
            "QQQ",
            "SPY",
            "NVDA",
            "MSFT",
            "AAPL",
            "AMZN",
            "META",
            "AVGO",
            "GOOGL",
            "GOOG",
            "TSLA",
            "NFLX",
            "AMD",
            "MU",
            "INTC",
            "QCOM",
            "SMCI",
        ]

        quotes = await self._snapshot_fetch_quotes(symbols)

        qqq = quotes.get("QQQ")
        spy = quotes.get("SPY")

        if not qqq:
            result = {
                "data": {},
                "status": "FINNHUB_ERROR",
                "provider": "Finnhub",
                "timestamp": time.time(),
            }

            # Do not cache hard provider failure for long.
            self._snapshot_cache = result
            self._snapshot_cache_time = time.time()

            return result

        data: Dict[str, Any] = {}

        # =====================================================
        # Provider evidence health
        # =====================================================
        # Quotes and candles are separate evidence channels.
        # A successful quote request must not imply that candle
        # evidence is also available.
        data["provider_quotes_available"] = bool(qqq)

        # Candle availability is tracked independently by the
        # downstream structure/liquidity calculations.
        data["provider_candle_evidence"] = "missing"

        # QQQ candle requests are required for intraday NQ structure.
        # If the structure calculation cannot be produced from candles,
        # mark the candle evidence as missing rather than treating the
        # quote feed as full market coverage.
        # =====================================================
        # QQQ / NQ structure
        # =====================================================

        qqq_change = qqq.get("dp")

        # Real NQ futures price for outcome/backtest resolution.
        # Keep QQQ price unchanged for the existing FIA signal logic.
        # Real NQ futures price is resolved by the backtest outcome
        # updater. Keep snapshot focused on the existing QQQ quote.
        try:
            nq_futures_price = await self.get_nq_futures_live_price()
        except Exception as exc:
            print(f"NQ futures live price unavailable in snapshot: {exc}")
            nq_futures_price = None

        data["nq_futures_price"] = nq_futures_price

        data["symbol"] = "QQQ"
        data["price"] = qqq.get("c")
        data["change"] = qqq.get("d")
        data["change_percent"] = qqq_change
        data["high"] = qqq.get("h")
        data["low"] = qqq.get("l")
        data["open"] = qqq.get("o")
        data["previous_close"] = qqq.get("pc")

        nq_signal = self.normalize_change(
            qqq_change
        )

        if nq_signal is not None:
            data["nq_structure"] = nq_signal
            # V6.6.2 TRUTH FIX: this value is derived from a single QQQ *quote*
            # percent-change scalar. No candle series was requested or received.
            # Declaring it "available" previously flipped forecast status
            # DEGRADED->LIVE and provider_health ERROR->LIVE on zero candle data.
            # DERIVED is a first-class state: it is not MISSING, and it is not LIVE.
            data["provider_candle_evidence"] = "derived_from_quote"
            data["nq_structure_basis"] = "QQQ_QUOTE_PERCENT_CHANGE_PROXY"

        # =====================================================
        # V6.6.2: REAL COMPLETED-BAR NQ/QQQ STRUCTURE
        # snapshot() previously issued ZERO candle requests, so "NQ structure" —
        # the single heaviest signal — was always a one-number quote proxy.
        # Fetch a real hourly series and compute structure from COMPLETED bars only.
        # =====================================================
        try:
            structure = await self.completed_bar_structure("QQQ", "60")
        except Exception as exc:  # never let structure enrichment break the snapshot
            print(f"Completed-bar structure unavailable: {exc}")
            structure = None

        # V6.6.6: publish WHY candles failed, when they did. Diagnostic only --
        # it never upgrades a proxy to real candle evidence.
        if not (structure and structure.get("score") is not None):
            if getattr(self, "_candle_failure", None):
                data["provider_candle_failure"] = dict(self._candle_failure)

        if structure and structure.get("score") is not None:
            data["nq_structure"] = structure["score"]
            data["provider_candle_evidence"] = "available"
            data["nq_structure_basis"] = structure["basis"]
            data["nq_structure_bars"] = structure["completed_bars"]
            data["nq_structure_last_bar_end_utc"] = structure["last_completed_bar_end_utc"]
            data["nq_structure_source"] = structure["source"]
            data["nq_structure_detail"] = structure["detail"]

        # =====================================================
        # SPX / SPY confirmation
        # =====================================================

        if spy:
            spy_change = spy.get("dp")

            spy_signal = self.normalize_change(
                spy_change
            )

            if spy_signal is not None:
                data["spx_confirmation"] = spy_signal
                data["spx_change_percent"] = spy_change
                data["spx_price"] = spy.get("c")

        # =====================================================
        # Price Action API structure
        # =====================================================

        price_action = await self.price_action_snapshot("QQQ", "5m")

        if price_action:
            data["price_action"] = price_action
            data["price_action_status"] = str(price_action.get("_fia_provider_status") or "LIVE")
        else:
            data["price_action"] = {"status": "unavailable","symbol": "QQQ","timeframe": "5m"}
            data["price_action_status"] = "UNAVAILABLE"

        # =====================================================
        # Mega-cap leadership
        # =====================================================

        self._snapshot_mega_cap(data, quotes)

        # =====================================================
        # Semiconductor leadership
        # =====================================================

        self._snapshot_semiconductors(data, quotes)

        # =====================================================
        # EQUAL-WEIGHT PARTICIPATION  (formerly mislabelled "Breadth")
        #
        # THIS IS NOT MARKET BREADTH. There is no advance/decline line, no
        # wide-universe sample and no NASDAQ-composite participation measure
        # behind it. It is the EQUAL-WEIGHTED mean normalised daily change of
        # the 15 tracked single-name large caps (symbols[2:], i.e. the quote
        # list minus QQQ and SPY):
        #
        #   NVDA MSFT AAPL AMZN META AVGO GOOGL GOOG TSLA NFLX AMD MU INTC QCOM SMCI
        #
        # Every constituent of "Semiconductors" (7) and of "Mega-cap leadership"
        # (10) is contained in this same 15-symbol set, so this factor shares
        # 100% of its constituents with those two signals. What it genuinely
        # measures is EQUAL-WEIGHT vs CAP-WEIGHT dispersion across the tracked
        # basket -- i.e. whether the move is broad within that basket or
        # concentrated in the heaviest names. That is real, useful information,
        # but it must not be presented as market breadth.
        # =====================================================

        self._snapshot_participation(data, quotes, symbols)

        # =====================================================
        # FRED macro
        # =====================================================

        await self._snapshot_macro_rates(data)

        # =====================================================
        # News — V6.7.2 truthful freshness failover
        # =====================================================

        await self._snapshot_news_intelligence(data)

        # =====================================================
        # Earnings intelligence
        # =====================================================

        await self._snapshot_earnings_calendar(data, finnhub_key)

        # =====================================================
        # Macro status — SOL56_MACRO_TRUTH_V1
        # =====================================================
        # A configured FRED key proves that macro *series* can be queried; it
        # does NOT prove that a timestamped economic-calendar surprise exists.
        # Treating that as a 0.0 "neutral calendar" vote silently converts
        # missing event evidence into evidence.  Fail closed instead.
        data["fred_macro_series_available"] = bool(self.keys["FRED_API_KEY"])
        data["macro"] = None
        data["macro_status"] = "missing_event_calendar"

        # =====================================================
        # Liquidity — NQ CHART TRUTH FIX
        # LIQUIDITY_TRUTH_FIX_V1
        # =====================================================
        # Monthly/weekly/daily AND session levels now come from the
        # SAME NQ=F futures price scale. QQQ is reference-only.
        try:
            from .nq_liquidity_truth import apply_nq_chart_liquidity
            await apply_nq_chart_liquidity(self, data)
            # V7.4 FIX: the success path never set liquidity_evidence_available, so
            # provider_reliability read a flag that only the FAILURE path and a dead
            # module (forexcom_chart_liquidity, never called from main.py) ever wrote.
            # Result: fully priced NQ levels were reported as a MISSING source.
            # Set it here from the REAL result, and keep the state honest:
            # EXPLICIT_CONTRACT -> available; CONTINUOUS_FALLBACK -> available but PROXY;
            # anything else, or no priced levels -> missing.
            _nq = data.get("nq_liquidity") or {}
            _levels = _nq.get("levels") or {}
            _priced = sum(1 for v in _levels.values() if v is not None)
            _quality = str(_nq.get("source_quality") or "").upper()
            _available = bool(_priced) and _quality in {"EXPLICIT_CONTRACT", "CONTINUOUS_FALLBACK"}
            data["liquidity_evidence_available"] = _available
            data["liquidity_evidence"] = {
                "nq": ("explicit_contract" if _quality == "EXPLICIT_CONTRACT"
                       else "continuous_fallback_proxy" if _quality == "CONTINUOUS_FALLBACK"
                       else "missing"),
                "nq_symbol": _nq.get("symbol"),
                "levels_priced": _priced,
                "levels_total": len(_levels),
                "source_quality": _quality or "MISSING",
                "is_proxy": _quality == "CONTINUOUS_FALLBACK",
                "qqq_reference": ("available" if (data.get("qqq_liquidity") or {}).get("levels") else "missing"),
            }
        except Exception as e:
            data["nq_liquidity"] = {
                "instrument": "NQ",
                "current_price": data.get("nq_futures_price"),
                "levels": {},
                "source": "missing",
                "primary_chart_liquidity": True,
            }
            data["qqq_liquidity"] = {
                "instrument": "QQQ",
                "current_price": data.get("price"),
                "levels": {},
                "source": "missing",
                "primary_chart_liquidity": False,
            }
            data["liquidity_evidence"] = {"nq": "missing", "qqq_reference": "missing"}
            data["liquidity_evidence_available"] = False
            print(f"NQ liquidity truth fix error -> {e}")

        # =====================================================
        # Provider coverage
        # =====================================================

        data["provider_quotes_available"] = len(
            quotes
        )

        data["provider_quotes_requested"] = len(
            symbols
        )

        # ---------------------------------------------------------- V6.6.8
        # QUOTE FRESHNESS IS THE AGE OF THE OBSERVATION, NOT OF THE FETCH.
        # source_health.market_quotes.age_seconds was hardcoded 0.0, i.e. the age
        # of the HTTP request, which is 0 by construction. A Friday close fetched
        # on Monday therefore reported as a live 0-second-old quote. Finnhub's
        # quote payload carries `t`, the exchange timestamp of the print; it is
        # used here so the freshness gate and the truth gate judge the EVIDENCE.
        self._snapshot_quote_freshness(data, quotes)

        # =====================================================
        # Phase 23 — source reliability / direct DXY / cleaner US10Y
        # =====================================================
        try:
            from .provider_reliability import enrich_provider_reliability
            await enrich_provider_reliability(self, data)
        except Exception as exc:
            # Reliability enrichment must never crash the base snapshot.
            print(f"Phase23 reliability enrichment error -> {exc}")
            data["provider_health_status"] = "DEGRADED"
            data["provider_health"] = {
                "overall": "DEGRADED",
                "score": 0.0,
                "critical_missing": ["reliability_enrichment"],
                "stale_sources": [],
                "fallback_active": [],
                "available_sources": [],
                "missing_sources": ["reliability_enrichment"],
                "rule": "Phase23 enrichment failed; base snapshot preserved.",
            }

        # =====================================================
        # Final snapshot
        # =====================================================

        _overall = str((data.get("provider_health") or {}).get("overall") or "DEGRADED").upper()
        result = {
            "data": data,
            "status": _overall if _overall in {"LIVE","DEGRADED","ERROR"} else "DEGRADED",
            "provider": "Finnhub + Polygon fallback",
            "timestamp": time.time(),
        }

        self._snapshot_cache = result
        self._snapshot_cache_time = time.time()

        return result

    async def _snapshot_fetch_quotes(self, symbols):
        """INFRASTRUCTURE: fan-out quote transport and response assembly."""
        quote_results = await asyncio.gather(
            *(self.finnhub_quote(symbol) for symbol in symbols),
            return_exceptions=True,
        )

        quotes = {}

        for symbol, result in zip(
            symbols,
            quote_results,
        ):
            if isinstance(result, Exception):
                print(
                    f"Quote error {symbol} -> {result}"
                )
                continue

            if isinstance(result, dict):
                quotes[symbol] = result

        return quotes

    async def _snapshot_earnings_calendar(self, data, finnhub_key):
        """PROTOCOL: earnings-calendar eligibility and catalyst admission."""
        try:

            earnings = await self.get(
                'https://' + 'finnhub.io/api/v1/calendar/earnings',
                {
                    "from": time.strftime(
                        "%Y-%m-%d"
                    ),
                    "to": time.strftime(
                        "%Y-%m-%d",
                        time.localtime(
                            time.time()
                            + 7 * 86400
                        ),
                    ),
                    "token": finnhub_key,
                },
                timeout=15,
            )

            events = (
                earnings or {}
            ).get(
                "earningsCalendar",
                [],
            )

            tracked = {
                "NVDA",
                "MSFT",
                "AAPL",
                "AMZN",
                "META",
                "AVGO",
                "GOOGL",
                "GOOG",
                "TSLA",
                "NFLX",
                "AMD",
                "MU",
                "INTC",
                "QCOM",
                "SMCI",
            }

            tracked_events = [
                event
                for event in events
                if event.get("symbol")
                in tracked
            ]

            positive = 0
            negative = 0
            counted = 0

            for event in tracked_events:

                actual = event.get(
                    "epsActual"
                )

                estimate = event.get(
                    "epsEstimate"
                )

                try:

                    if (
                        actual is None
                        or estimate is None
                    ):
                        continue

                    actual = float(actual)
                    estimate = float(estimate)

                    if actual > estimate:
                        positive += 1
                        counted += 1

                    elif actual < estimate:
                        negative += 1
                        counted += 1

                except (
                    TypeError,
                    ValueError,
                ):
                    continue

            data["earnings_calendar_available"] = True
            data["earnings_catalyst_risk"] = bool(tracked_events)
            if counted:
                data["earnings"] = max(-1.0,min(1.0,(positive-negative)/counted))
                data["earnings_status"] = "released_surprise"
            elif tracked_events:
                # Upcoming calendar risk is NOT a directional vote.
                data["earnings"] = None
                data["earnings_status"] = "upcoming_only_no_released_surprise"
            else:
                data["earnings"] = None
                data["earnings_status"] = "no_tracked_events"

            data["earnings_events"] = len(tracked_events)

            data[
                "earnings_surprises_counted"
            ] = counted

            data["earnings_positive"] = positive
            data["earnings_negative"] = negative

        except Exception as e:
            data["earnings"] = None
            data["earnings_calendar_available"] = False
            data["earnings_status"] = "provider_error"
            data["earnings_catalyst_risk"] = False
            print(f"Earnings intelligence error -> {e}")


    def _snapshot_quote_freshness(self, data, quotes):
        """PROTOCOL: staleness evidence derived from quote timestamps."""
        _q_ts = []
        for _sym, _q in quotes.items():
            _t = _q.get("t") if isinstance(_q, dict) else None
            try:
                _t = float(_t)
            except (TypeError, ValueError):
                continue
            if _t > 0:
                _q_ts.append(_t)
        if _q_ts:
            _newest = max(_q_ts)
            _obs = datetime.fromtimestamp(_newest, timezone.utc)
            data["quote_observed_at"] = _obs.isoformat()
            data["quote_observation_age_seconds"] = round(
                (datetime.now(timezone.utc) - _obs).total_seconds(), 1)
            data["quote_timestamp_quality"] = "PROVIDER_EXCHANGE_TIMESTAMP"
            data["quote_symbols_with_timestamp"] = len(_q_ts)
        else:
            data["quote_observed_at"] = None
            data["quote_observation_age_seconds"] = None
            data["quote_timestamp_quality"] = "NO_PROVIDER_TIMESTAMP_AVAILABLE"
            data["quote_symbols_with_timestamp"] = 0











