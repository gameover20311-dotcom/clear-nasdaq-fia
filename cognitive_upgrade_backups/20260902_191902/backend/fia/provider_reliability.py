# PHASE23_DATA_RELIABILITY_V1
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

UTC = timezone.utc


@dataclass
class MarketObservation:
    symbol: str
    value: Optional[float]
    previous: Optional[float]
    change_percent: Optional[float]
    observed_at: Optional[str]
    age_seconds: Optional[float]
    freshness: str
    source: str


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def classify_freshness(age_seconds: Optional[float]) -> str:
    """Market-timestamp freshness, tolerant of normal overnight closures."""
    if age_seconds is None:
        return "unknown"
    if age_seconds <= 20 * 60:
        return "live"
    if age_seconds <= 6 * 3600:
        return "recent"
    if age_seconds <= 72 * 3600:
        return "delayed"
    return "stale"


def dxy_signal(change_percent: Optional[float]) -> Optional[float]:
    """Convert REAL DXY movement into NQ directional pressure.

    Rising DXY is normally pressure on growth/NQ, so positive DXY change
    produces a negative FIA score. 0.75% intraday DXY movement saturates
    the signal; the existing FIA DXY weight is NOT changed.
    """
    if change_percent is None:
        return None
    return clamp(-float(change_percent) / 0.75)


def tnx_to_yield(raw_value: Optional[float]) -> Optional[float]:
    """Yahoo ^TNX is commonly quoted as 10x the 10Y yield (e.g. 47.3=4.73%)."""
    if raw_value is None:
        return None
    value = float(raw_value)
    return value / 10.0 if value > 20.0 else value


def us10y_signal(yield_percent: Optional[float]) -> Optional[float]:
    """Preserve the project's validated pre-Phase23 US10Y bucket semantics."""
    if yield_percent is None:
        return None
    value = float(yield_percent)
    if value < 4.0:
        return 0.35
    if value < 4.5:
        return 0.0
    return -0.5


def _iso_timestamp(value: Any) -> Optional[str]:
    try:
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    except Exception:
        return None


def _age_seconds(value: Any) -> Optional[float]:
    try:
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        age = (datetime.now(UTC) - value.astimezone(UTC)).total_seconds()
        return max(0.0, float(age))
    except Exception:
        return None


def _load_yahoo_observation_sync(symbol: str) -> Optional[MarketObservation]:
    """Load recent 5m data and compute change versus previous daily close.

    No API key is required. The source is explicitly labelled Yahoo Finance;
    it may be delayed depending on the instrument/session.
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        intraday = ticker.history(period="5d", interval="5m", auto_adjust=False)
        daily = ticker.history(period="5d", interval="1d", auto_adjust=False)

        if intraday is None or intraday.empty:
            return None

        closes = intraday["Close"].dropna()
        if closes.empty:
            return None

        latest = float(closes.iloc[-1])
        observed_idx = closes.index[-1]
        observed_at = _iso_timestamp(observed_idx)
        age_seconds = _age_seconds(observed_idx)

        previous = None
        if daily is not None and not daily.empty:
            daily_closes = daily["Close"].dropna()
            if len(daily_closes) >= 2:
                # Latest daily bar can be partial while session is open.
                previous = float(daily_closes.iloc[-2])
            elif len(daily_closes) == 1:
                previous = float(daily_closes.iloc[-1])

        change_percent = None
        if previous not in (None, 0):
            change_percent = (latest / previous - 1.0) * 100.0

        return MarketObservation(
            symbol=symbol,
            value=latest,
            previous=previous,
            change_percent=change_percent,
            observed_at=observed_at,
            age_seconds=age_seconds,
            freshness=classify_freshness(age_seconds),
            source=f"Yahoo Finance {symbol}",
        )
    except Exception as exc:
        print(f"Phase23 Yahoo provider error {symbol} -> {exc}")
        return None


async def yahoo_observation(symbol: str) -> Optional[MarketObservation]:
    return await asyncio.to_thread(_load_yahoo_observation_sync, symbol)


def _source_item(
    *,
    available: bool,
    source: str,
    freshness: str,
    status: Optional[str] = None,
    observed_at: Optional[str] = None,
    age_seconds: Optional[float] = None,
    fallback: bool = False,
    value: Optional[float] = None,
    change_percent: Optional[float] = None,
    note: str = "",
) -> Dict[str, Any]:
    if status is None:
        if not available:
            status = "missing"
        elif freshness == "stale":
            status = "stale"
        elif fallback:
            status = "fallback"
        else:
            status = "live"

    return {
        "available": bool(available),
        "status": str(status),
        "source": str(source),
        "freshness": str(freshness),
        "observed_at": observed_at,
        "age_seconds": round(float(age_seconds), 1) if age_seconds is not None else None,
        "fallback": bool(fallback),
        "value": value,
        "change_percent": change_percent,
        "note": note,
    }


def build_provider_health(source_health: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic source-health validator.

    Critical: market quotes, candle evidence, DXY, US10Y.
    Fallback is allowed and surfaced; it is not silently treated as primary.
    """
    critical = ("market_quotes", "candles", "dxy", "us10y")
    optional = ("news", "macro", "earnings", "liquidity")

    critical_missing = []
    stale_sources = []
    fallback_active = []
    available = []
    missing = []

    for name, item in source_health.items():
        if item.get("available"):
            available.append(name)
        else:
            missing.append(name)
        if item.get("freshness") == "stale" or item.get("status") == "stale":
            stale_sources.append(name)
        if item.get("fallback"):
            fallback_active.append(name)

    for name in critical:
        item = source_health.get(name) or {}
        if not item.get("available") or item.get("status") in {"missing", "error"}:
            critical_missing.append(name)

    if critical_missing:
        overall = "ERROR"
    elif any(name in stale_sources for name in critical):
        overall = "DEGRADED"
    else:
        overall = "LIVE"

    total = len(critical) + len(optional)
    present = sum(1 for name in (*critical, *optional) if (source_health.get(name) or {}).get("available"))
    score = round((present / total) * 100.0, 1) if total else 0.0

    return {
        "overall": overall,
        "score": score,
        "critical_missing": critical_missing,
        "stale_sources": stale_sources,
        "fallback_active": fallback_active,
        "available_sources": available,
        "missing_sources": missing,
        "checked_at": datetime.now(UTC).isoformat(),
        "rule": "Fallbacks are explicit; missing/stale critical sources cannot report full health.",
    }


async def enrich_provider_reliability(hub: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Enrich an existing Phase22 snapshot without changing FIA weights."""
    now_iso = datetime.now(UTC).isoformat()

    # Preserve the legacy DFF-derived DXY proxy ONLY as an explicit fallback.
    legacy_dxy_proxy = data.get("dxy")
    data["dxy_rate_proxy"] = legacy_dxy_proxy

    dxy_obs, tnx_obs = await asyncio.gather(
        yahoo_observation("DX-Y.NYB"),
        yahoo_observation("^TNX"),
        return_exceptions=False,
    )

    source_health: Dict[str, Dict[str, Any]] = {}

    quote_count = data.get("provider_quotes_available")
    quote_available = bool(quote_count)
    source_health["market_quotes"] = _source_item(
        available=quote_available,
        source="Finnhub",
        freshness="request_live" if quote_available else "missing",
        observed_at=now_iso if quote_available else None,
        age_seconds=0.0 if quote_available else None,
        note=f"{quote_count or 0} tracked quotes returned in current snapshot request.",
    )

    candle_available = str(data.get("provider_candle_evidence", "missing")).lower() == "available"
    source_health["candles"] = _source_item(
        available=candle_available,
        source="Finnhub candles + Polygon fallback",
        freshness="request_live" if candle_available else "missing",
        observed_at=now_iso if candle_available else None,
        age_seconds=0.0 if candle_available else None,
        fallback=False,
        note="Structure evidence health; exact upstream may be Finnhub or Polygon fallback.",
    )

    # ----------------------------------------------------------
    # REAL DXY
    # ----------------------------------------------------------
    if isinstance(dxy_obs, MarketObservation) and dxy_obs.value is not None:
        signal = dxy_signal(dxy_obs.change_percent)
        data["dxy_value"] = round(float(dxy_obs.value), 4)
        data["dxy_change_percent"] = (
            round(float(dxy_obs.change_percent), 4)
            if dxy_obs.change_percent is not None else None
        )
        data["dxy"] = signal
        data["dxy_source"] = dxy_obs.source
        data["dxy_source_timestamp"] = dxy_obs.observed_at
        source_health["dxy"] = _source_item(
            available=signal is not None,
            source=dxy_obs.source,
            freshness=dxy_obs.freshness,
            observed_at=dxy_obs.observed_at,
            age_seconds=dxy_obs.age_seconds,
            fallback=False,
            value=data.get("dxy_value"),
            change_percent=data.get("dxy_change_percent"),
            note="Direct US Dollar Index level/change; FIA score is inverse DXY pressure on NQ.",
        )
    elif legacy_dxy_proxy is not None:
        # Never label DFF as real DXY.
        data["dxy"] = legacy_dxy_proxy
        data["dxy_value"] = None
        data["dxy_change_percent"] = None
        data["dxy_source"] = "FRED DFF rate proxy fallback"
        data["dxy_source_timestamp"] = None
        source_health["dxy"] = _source_item(
            available=True,
            source="FRED DFF rate proxy",
            freshness="fallback",
            fallback=True,
            value=None,
            note="Direct DXY unavailable; existing DFF proxy retained explicitly as fallback.",
        )
    else:
        data["dxy"] = None
        data["dxy_value"] = None
        data["dxy_source"] = "missing"
        source_health["dxy"] = _source_item(
            available=False, source="missing", freshness="missing",
            note="Neither direct DXY nor legacy rate proxy is available.",
        )

    # ----------------------------------------------------------
    # CLEANER / FRESHER US10Y
    # ----------------------------------------------------------
    existing_us10y_value = data.get("us10y_value")
    existing_us10y_signal = data.get("us10y")

    tnx_yield = None
    if isinstance(tnx_obs, MarketObservation):
        tnx_yield = tnx_to_yield(tnx_obs.value)

    if tnx_yield is not None:
        data["us10y_value"] = round(float(tnx_yield), 4)
        data["us10y"] = us10y_signal(tnx_yield)
        data["us10y_source"] = "Yahoo Finance ^TNX"
        data["us10y_source_timestamp"] = tnx_obs.observed_at
        raw_change = tnx_obs.change_percent
        data["us10y_change_percent"] = round(float(raw_change), 4) if raw_change is not None else None
        source_health["us10y"] = _source_item(
            available=True,
            source="Yahoo Finance ^TNX",
            freshness=tnx_obs.freshness,
            observed_at=tnx_obs.observed_at,
            age_seconds=tnx_obs.age_seconds,
            fallback=False,
            value=data.get("us10y_value"),
            change_percent=data.get("us10y_change_percent"),
            note="Intraday ^TNX converted to 10Y yield percent; existing FIA yield buckets preserved.",
        )
    elif existing_us10y_value is not None:
        data["us10y_value"] = existing_us10y_value
        data["us10y"] = existing_us10y_signal
        data["us10y_source"] = "FRED DGS10 fallback"
        data["us10y_source_timestamp"] = None
        source_health["us10y"] = _source_item(
            available=True,
            source="FRED DGS10",
            freshness="fallback",
            fallback=True,
            value=float(existing_us10y_value),
            note="Intraday ^TNX unavailable; FRED DGS10 retained as explicit fallback.",
        )
    else:
        data["us10y"] = None
        data["us10y_source"] = "missing"
        source_health["us10y"] = _source_item(
            available=False, source="missing", freshness="missing",
            note="Neither ^TNX nor FRED DGS10 is available.",
        )

    news_status = str(data.get("news_status") or "missing")
    news_available = news_status.startswith("live")
    source_health["news"] = _source_item(
        available=news_available,
        source="NewsAPI",
        freshness="request_live" if news_available else "missing",
        status=news_status,
        observed_at=now_iso if news_available else None,
        age_seconds=0.0 if news_available else None,
        note=f"articles={data.get('news_articles', 0)}, scored={data.get('news_scored_articles', 0)}",
    )

    macro_status = str(data.get("macro_status") or "missing")
    macro_available = "missing" not in macro_status.lower() and "unavailable" not in macro_status.lower()
    source_health["macro"] = _source_item(
        available=macro_available,
        source="FRED",
        freshness="request_live" if macro_available else "missing",
        status="live" if macro_available else "missing",
        observed_at=now_iso if macro_available else None,
        age_seconds=0.0 if macro_available else None,
        note=macro_status,
    )

    earnings_available = data.get("earnings") is not None
    source_health["earnings"] = _source_item(
        available=earnings_available,
        source="Finnhub earnings calendar",
        freshness="request_live" if earnings_available else "missing",
        observed_at=now_iso if earnings_available else None,
        age_seconds=0.0 if earnings_available else None,
        note=f"tracked events={data.get('earnings_events', 0)}",
    )

    liquidity_available = bool(data.get("liquidity_evidence_available"))
    source_health["liquidity"] = _source_item(
        available=liquidity_available,
        source="QQQ period candles + NQ futures session candles",
        freshness="request_live" if liquidity_available else "missing",
        observed_at=now_iso if liquidity_available else None,
        age_seconds=0.0 if liquidity_available else None,
        note=str(data.get("liquidity_evidence") or {}),
    )

    data["source_health"] = source_health
    data["provider_health"] = build_provider_health(source_health)
    data["provider_health_status"] = data["provider_health"]["overall"]
    data["provider_health_score"] = data["provider_health"]["score"]
    return data
