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

"""CLEAR NASDAQ — providers.py split, INFRASTRUCTURE half.

INFRASTRUCTURE — machinery that must NOT alter scientific meaning.

Transport, construction, raw provider fetches and value coercion helpers.

SPLIT MECHANICS
This module holds method bodies moved VERBATIM out of providers.py. It is a
mixin, not a standalone class: ProviderHub composes all three, so every
self.<method> call resolves exactly as it did before and the public
ProviderHub API is unchanged. Nothing here was rewritten, reordered inside a
method, or retyped; the split is a move.
"""


class InfrastructureMixin:
    """
    Central provider layer for CLEAR NASDAQ FIA.

    Providers:
      - Finnhub: market quotes, candles, earnings
      - FRED: rates / macro
      - NewsAPI: news sentiment

    Liquidity:
      - Monthly high / low
      - Weekly high / low
      - Daily high / low
      - Asia high / low
      - London high / low
      - New York high / low
    """

    NY_TZ = ZoneInfo("America/New_York")
    UTC = timezone.utc

    # Small cache prevents /snapshot and /forecast from seeing
    # different provider states when called seconds apart.
    SNAPSHOT_CACHE_SECONDS = 8
    def __init__(self):
        self.keys = {
            k: os.getenv(k, "")
            for k in [
                "FRED_API_KEY",
                "ALPHAVANTAGE_API_KEY",
                "FINNHUB_API_KEY",
                "POLYGON_API_KEY",
                "NEWS_API_KEY",
                "PRICEACTION_API_KEY",
            ]
        }

        # V6.6.6 DIAGNOSTIC: why the candle series failed, if it did.
        # A missing POLYGON_API_KEY and a REJECTED POLYGON_API_KEY previously
        # produced byte-identical /api/provider/health output -- both simply
        # reported candles as 'derived'. The reason existed only on stdout, which
        # is not readable on a managed host, so a configuration fault was
        # indistinguishable from a provider outage. This records the reason so it
        # can be surfaced. It changes no availability semantics.
        self._candle_failure: Optional[Dict[str, Any]] = None

        self._snapshot_cache: Optional[Dict[str, Any]] = None
        self._snapshot_cache_time: float = 0.0
        self._price_action_cache: Dict[tuple[str, str], tuple[float, Dict[str, Any]]] = {}
        self._price_action_cooldown_until: Dict[tuple[str, str], float] = {}
        self.PRICE_ACTION_CACHE_SECONDS = 60.0
        self.PRICE_ACTION_RATE_LIMIT_BACKOFF_SECONDS = 300.0
        # V6.7.2: live-news provider selection is cached separately so a stale
        # NewsAPI feed cannot cause a Finnhub fallback request every 8-second
        # snapshot refresh. One minute is negligible for 4H/8H research while
        # materially reducing provider-rate pressure.
        self._live_news_cache: Optional[Dict[str, Any]] = None
        self._live_news_cache_time: float = 0.0
        self.LIVE_NEWS_CACHE_SECONDS = 60.0
    async def get(
        self,
        url: str,
        params: Optional[dict] = None,
        timeout: float = 10,
        headers: Optional[dict] = None,
    ):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            # SECURITY: never stringify provider exceptions here. httpx embeds the
            # fully-expanded request URL in HTTPStatusError, including query-string
            # credentials such as Finnhub token=... and Polygon apiKey=....
            # Log only scheme/host/path plus status/type; never query parameters.
            try:
                from urllib.parse import urlsplit
                parts = urlsplit(str(url))
                safe_url = f"{parts.scheme}://{parts.netloc}{parts.path}"
            except Exception:
                safe_url = "<provider-url-redacted>"

            status = None
            if isinstance(e, httpx.HTTPStatusError) and getattr(e, "response", None) is not None:
                status = getattr(e.response, "status_code", None)
            if status is not None:
                print(f"Provider error: {safe_url} -> HTTP {status} ({type(e).__name__})")
            else:
                print(f"Provider error: {safe_url} -> {type(e).__name__}")
            return None
    @staticmethod
    def clamp(value: float, low: float = -1.0, high: float = 1.0):
        return max(low, min(high, value))
    @staticmethod
    def safe_float(value):
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
    async def finnhub_quote(self, symbol: str):
        key = self.keys["FINNHUB_API_KEY"]

        if not key:
            return None

        return await self.get(
            'https://' + 'finnhub.io/api/v1/quote',
            {
                "symbol": symbol,
                "token": key,
            },
        )
    async def _yahoo_chart_candles(
        self,
        symbol: str,
        resolution: str,
        start_ts: int,
        end_ts: int,
    ):
        """Keyless Yahoo chart fallback, normalized to Finnhub candle shape.

        This is a live fallback only. Timestamps remain provider aggregate-window
        START timestamps; completed_bar_structure() remains the single authority
        that rejects a still-forming final bar before any structure score is used.
        """
        from urllib.parse import quote

        interval_map = {
            "D": "1d",
            "5": "5m", "5m": "5m",
            "15": "15m", "15m": "15m",
            "30": "30m", "30m": "30m",
            "60": "60m", "60m": "60m",
        }
        interval = interval_map.get(str(resolution))
        if not interval:
            return None

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(str(symbol), safe='')}"
        payload = await self.get(
            url,
            {
                "period1": int(start_ts),
                "period2": int(end_ts) + 60,
                "interval": interval,
                "includePrePost": "true",
                "events": "div,splits",
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if not isinstance(payload, dict):
            return None

        chart = payload.get("chart") or {}
        if chart.get("error"):
            return None
        results = chart.get("result") or []
        if not results or not isinstance(results[0], dict):
            return None
        result = results[0]
        stamps = list(result.get("timestamp") or [])
        indicators = result.get("indicators") or {}
        quotes = indicators.get("quote") or []
        if not stamps or not quotes or not isinstance(quotes[0], dict):
            return None
        q = quotes[0]
        closes_raw = list(q.get("close") or [])
        highs_raw = list(q.get("high") or [])
        lows_raw = list(q.get("low") or [])
        opens_raw = list(q.get("open") or [])
        volumes_raw = list(q.get("volume") or [])

        timestamps, highs, lows, closes, opens, volumes = [], [], [], [], [], []
        for i, ts in enumerate(stamps):
            try:
                close = closes_raw[i] if i < len(closes_raw) else None
                if ts is None or close is None:
                    continue
                close_f = float(close)
                high = highs_raw[i] if i < len(highs_raw) else None
                low = lows_raw[i] if i < len(lows_raw) else None
                open_ = opens_raw[i] if i < len(opens_raw) else None
                volume = volumes_raw[i] if i < len(volumes_raw) else None
                timestamps.append(int(ts))
                highs.append(float(high) if high is not None else close_f)
                lows.append(float(low) if low is not None else close_f)
                closes.append(close_f)
                opens.append(float(open_) if open_ is not None else close_f)
                volumes.append(float(volume) if volume is not None else 0.0)
            except (TypeError, ValueError, OverflowError, IndexError):
                continue

        if not timestamps:
            return None
        return {
            "s": "ok",
            "t": timestamps,
            "h": highs,
            "l": lows,
            "c": closes,
            "o": opens,
            "v": volumes,
            "_fia_candle_source": "yahoo_chart_fallback",
        }
    async def fred_series(self, series_id: str):
        key = self.keys["FRED_API_KEY"]

        if not key:
            return None

        return await self.get(
            "https://api.stlouisfed.org/fred/series/observations",
            {
                "series_id": series_id,
                "api_key": key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 5,
            },
        )
    async def price_action_snapshot(
        self,
        symbol: str = "QQQ",
        timeframe: str = "5m",
    ):
        key = self.keys.get("PRICEACTION_API_KEY")
        if not key:
            return None

        cache_key=(str(symbol),str(timeframe))
        now=time.time()
        cached=self._price_action_cache.get(cache_key)
        if cached and now-cached[0] < self.PRICE_ACTION_CACHE_SECONDS:
            out=dict(cached[1]); out["_fia_provider_status"]="LIVE_CACHED"; return out

        cooldown=float(self._price_action_cooldown_until.get(cache_key,0.0) or 0.0)
        if now < cooldown:
            if cached:
                out=dict(cached[1]); out["_fia_provider_status"]="STALE_CACHED_RATE_LIMIT"; out["_fia_retry_after_seconds"]=round(cooldown-now,1); return out
            return None

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    "https://priceactionapi.com/v1/snapshot",
                    headers={"Authorization": f"Bearer {key}"},
                    params={"symbol": symbol,"timeframe": timeframe},
                )
                if response.status_code == 429:
                    retry=response.headers.get("Retry-After")
                    try: wait=max(30.0,float(retry)) if retry else self.PRICE_ACTION_RATE_LIMIT_BACKOFF_SECONDS
                    except Exception: wait=self.PRICE_ACTION_RATE_LIMIT_BACKOFF_SECONDS
                    self._price_action_cooldown_until[cache_key]=now+min(wait,3600.0)
                    if cached:
                        out=dict(cached[1]); out["_fia_provider_status"]="STALE_CACHED_RATE_LIMIT"; out["_fia_retry_after_seconds"]=round(min(wait,3600.0),1); return out
                    return None
                response.raise_for_status()
                obj=response.json()
                if not isinstance(obj,dict): return None
                self._price_action_cache[cache_key]=(time.time(),dict(obj))
                obj=dict(obj); obj["_fia_provider_status"]="LIVE"
                self._price_action_cooldown_until.pop(cache_key,None)
                return obj
        except Exception as e:
            if cached:
                out=dict(cached[1]); out["_fia_provider_status"]="STALE_CACHED_PROVIDER_ERROR"; return out
            print(f"Price Action API error -> {e}")
            return None
    async def news_sentiment(self, symbol: str = "QQQ"):
        key = self.keys["NEWS_API_KEY"]

        if not key:
            return None

        return await self.get(
            'https://' + 'newsapi.org/v2/everything',
            {
                "q": f"{symbol} OR Nasdaq OR technology stocks",
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 20,
                "apiKey": key,
            },
        )
    async def finnhub_market_news(self, category: str = "general"):
        """Fetch live market news from Finnhub."""
        key = self.keys.get("FINNHUB_API_KEY", "")

        if not key:
            return []

        data = await self.get(
            "https://finnhub.io/api/v1/news",
            {
                "category": category,
                "token": key,
            },
            timeout=15,
        )

        return data if isinstance(data, list) else []
    async def finnhub_company_news(
        self,
        symbol: str,
        days: int = 7,
    ):
        """Fetch recent company-specific news from Finnhub."""
        key = self.keys.get("FINNHUB_API_KEY", "")

        if not key:
            return []

        end_date = self.now_ny().date()
        start_date = end_date - timedelta(days=days)

        data = await self.get(
            "https://finnhub.io/api/v1/company-news",
            {
                "symbol": symbol,
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "token": key,
            },
            timeout=15,
        )

        return data if isinstance(data, list) else []
    @classmethod
    def now_ny(cls):
        return datetime.now(cls.NY_TZ)
    @classmethod
    def datetime_to_ts(cls, dt: datetime) -> int:
        return int(dt.timestamp())
    async def polygon_futures_candles(
        self,
        ticker: str,
        multiplier: int = 5,
        timespan: str = "minute",
        start_ts: int = None,
        end_ts: int = None,
    ):
        """
        SOL56_V2_MASSIVE_FUTURES_TRUTH

        Compatibility method name preserved for existing callers.

        Uses Massive Futures REST v1 explicit-contract aggregates.
        Returns the normalized legacy structure expected by FIA:
        t/h/l/c/v in Unix seconds / floats.

        No continuous NQ=F proxy is introduced here.
        """

        import os

        massive_key = (
            self.keys.get("MASSIVE_API_KEY")
            or self.keys.get("POLYGON_API_KEY")
            or os.getenv("MASSIVE_API_KEY")
            or os.getenv("POLYGON_API_KEY")
        )

        if not massive_key:
            print(
                "Explicit NQ futures unavailable: "
                "Massive/Polygon API key missing."
            )
            return None

        if start_ts is None:
            start_ts = self.datetime_to_ts(
                self.now_ny() - timedelta(days=8)
            )

        if end_ts is None:
            end_ts = self.datetime_to_ts(self.now_ny())

        unit = str(timespan or "minute").lower()

        unit_map = {
            "second": "sec",
            "seconds": "sec",
            "sec": "sec",
            "minute": "min",
            "minutes": "min",
            "min": "min",
            "hour": "hour",
            "hours": "hour",
            "day": "session",
            "days": "session",
            "session": "session",
            "week": "week",
            "month": "month",
            "quarter": "quarter",
            "year": "year",
        }

        massive_unit = unit_map.get(unit)

        if not massive_unit:
            print(
                f"Unsupported Massive futures timespan: {timespan}"
            )
            return None

        resolution = f"{int(multiplier)}{massive_unit}"

        url = (
            "https://"
            + f"api.massive.com/futures/v1/aggs/{ticker}"
        )

        params = {
            "resolution": resolution,
            "sort": "window_start.asc",
            "limit": 50000,
            "apiKey": massive_key,
            "window_start.gte": int(start_ts) * 1_000_000_000,
            "window_start.lte": int(end_ts) * 1_000_000_000,
        }

        response = await self.get(
            url,
            params,
            timeout=20,
        )

        if not isinstance(response, dict):
            print(
                f"Massive NQ futures returned no response for {ticker}."
            )
            return None

        results = response.get("results") or []

        if not results:
            print(
                f"Massive NQ futures returned no candles for {ticker}."
            )
            return None

        timestamps = []
        highs = []
        lows = []
        closes = []
        volumes = []

        for row in results:
            try:
                ts_ns = row.get("window_start")
                high = row.get("high")
                low = row.get("low")
                close = row.get("close")
                volume = row.get("volume", 0)

                if (
                    ts_ns is None
                    or high is None
                    or low is None
                    or close is None
                ):
                    continue

                timestamps.append(
                    int(ts_ns) // 1_000_000_000
                )
                highs.append(float(high))
                lows.append(float(low))
                closes.append(float(close))
                volumes.append(float(volume or 0))

            except (
                TypeError,
                ValueError,
                OverflowError,
            ):
                continue

        if not timestamps:
            return None

        return {
            "s": "ok",
            "t": timestamps,
            "h": highs,
            "l": lows,
            "c": closes,
            "v": volumes,
            "ticker": ticker,
            "provider": "MASSIVE_FUTURES_V1",
            "resolution": resolution,
        }
    async def get_nq_futures_live_price(self):
        """Get the latest available NQ futures price from yfinance."""
        try:
            import yfinance as yf

            def load():
                ticker = yf.Ticker("NQ=F")
                data = ticker.history(
                    period="1d",
                    interval="1m",
                    auto_adjust=False,
                )
                if data is None or data.empty:
                    return None
                return float(data["Close"].dropna().iloc[-1])

            return await asyncio.to_thread(load)

        except Exception as exc:
            print(f"NQ futures live price unavailable: {exc}")
            return None
