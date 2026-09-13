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
    evidence_state: Optional[str] = None,
) -> Dict[str, Any]:
    if status is None:
        if not available:
            status = "missing"
        elif freshness == "stale":
            status = "stale"
        elif fallback:
            status = "fallback"
        elif freshness == "unknown":
            # V6.6.2: unknown age is not evidence of freshness. Reporting it as
            # "live" made data of indeterminate age indistinguishable from a
            # current observation.
            status = "unknown_age"
        elif freshness == "delayed":
            # V6.6.2: "delayed" spans up to 72h. Calling that "live" let data more
            # than a day old drive the dashboard as if it were current.
            status = "delayed"
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
        "evidence_state": evidence_state,
    }


def build_provider_health(source_health: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic source-health validator.

    Critical: market quotes, candle evidence, DXY, US10Y.
    Fallback is allowed and surfaced; it is not silently treated as primary.
    """
    critical = ("market_quotes", "candles", "dxy", "us10y")
    optional = ("news", "macro", "earnings", "liquidity", "volatility")

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


def _session_status(source: str, age_seconds, available: bool, now=None) -> str:
    """Truthful status word for a venue-based source.

    V6.6.8: "live" was applied to any available source regardless of how old the
    observation actually was, so a Friday close fetched on a holiday Monday read
    as live. A closed venue's last print is CURRENT_FOR_SESSION -- real, usable,
    but explicitly NOT current intraday evidence.
    """
    if not available:
        return "missing"
    try:
        from .market_sessions import session_state
        from .premove_watch import MAX_AGE_SECONDS_BY_SOURCE
        ceiling = float(MAX_AGE_SECONDS_BY_SOURCE.get(source, 21600.0))
        st = session_state(source, age_seconds, ceiling, now=now)
    except Exception:
        return "live" if age_seconds is not None else "unknown_age"
    fresh = st.get("freshness")
    if fresh == "LIVE":
        return "live"
    if fresh == "CURRENT_FOR_SESSION":
        return "current_for_session"
    if fresh == "UNKNOWN_AGE":
        return "unknown_age"
    return "stale"


async def enrich_provider_reliability(hub: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Enrich an existing Phase22 snapshot without changing FIA weights."""
    now_iso = datetime.now(UTC).isoformat()

    # Preserve the legacy DFF-derived DXY proxy ONLY as an explicit fallback.
    legacy_dxy_proxy = data.get("dxy")
    data["dxy_rate_proxy"] = legacy_dxy_proxy

    dxy_obs, tnx_obs, vix_obs = await asyncio.gather(
        yahoo_observation("DX-Y.NYB"),
        yahoo_observation("^TNX"),
        yahoo_observation("^VIX"),
        return_exceptions=False,
    )

    source_health: Dict[str, Dict[str, Any]] = {}

    quote_count = data.get("provider_quotes_available")
    quote_available = bool(quote_count)
    # V6.6.8 QUOTE FRESHNESS = AGE OF THE PRINT, NOT OF THE REQUEST.
    # age_seconds was hardcoded 0.0. On 2026-09-07 (Labor Day) that made a
    # Friday 16:00 ET close read as a 0-second-old live quote, and the truth gate
    # passed on it. The exchange timestamp from the provider is used instead.
    _q_obs = data.get("quote_observed_at")
    _q_age = data.get("quote_observation_age_seconds")
    _q_quality = str(data.get("quote_timestamp_quality") or "UNKNOWN")
    source_health["market_quotes"] = _source_item(
        available=quote_available,
        status=_session_status("market_quotes", _q_age, quote_available),
        source="Finnhub",
        freshness=("missing" if not quote_available
                   else ("unknown" if _q_age is None else "recent")),
        observed_at=(_q_obs if quote_available else None),
        age_seconds=(float(_q_age) if (quote_available and _q_age is not None) else None),
        evidence_state=("RELEASED_VERIFIED" if quote_available else "SOURCE_FAILURE"),
        note=(f"{quote_count or 0} tracked quotes returned in current snapshot request; "
              f"fetched_at={now_iso}; observed_at={_q_obs}; "
              f"observation_age_seconds={_q_age}; timestamp_quality={_q_quality}"),
    )

    # V6.6.2: only a real candle series counts as candle evidence. "derived_from_quote"
    # is a PROXY and must not be reported as an available candle source.
    _candle_state = str(data.get("provider_candle_evidence", "missing")).lower()
    candle_available = _candle_state == "available"
    candle_derived = _candle_state.startswith("derived")
    # V6.6.8 CANDLE FRESHNESS = AGE OF THE LAST COMPLETED BAR.
    # age_seconds was hardcoded 0.0 while the payload itself carried
    # nq_structure_last_bar_end_utc. On 2026-09-07 the last completed bar ended
    # 2026-09-04T22:00Z (Friday) and the source still reported "live, 0.0s".
    _bar_end = data.get("nq_structure_last_bar_end_utc")
    _bar_age = None
    if _bar_end:
        try:
            _bd = datetime.fromisoformat(str(_bar_end).replace("Z", "+00:00"))
            if _bd.tzinfo is None:
                _bd = _bd.replace(tzinfo=timezone.utc)
            _bar_age = round((datetime.now(timezone.utc) - _bd).total_seconds(), 1)
        except (ValueError, TypeError):
            _bar_age = None

    candle_source = str(data.get("nq_structure_source") or "")
    candle_fallback = candle_available and "fallback" in candle_source.lower()
    source_health["candles"] = _source_item(
        available=candle_available,
        status=(_session_status("candles", _bar_age, True) if candle_available
                else ("derived" if candle_derived else "missing")),
        source=((candle_source or "Candle provider unspecified") if candle_available
                else ("QQQ quote percent-change proxy (NO candle series fetched)" if candle_derived
                      else "Finnhub candles + Polygon fallback + Yahoo fallback")),
        freshness=(("recent" if _bar_age is not None else "unknown") if candle_available
                   else ("derived" if candle_derived else "missing")),
        observed_at=(_bar_end if candle_available else None),
        age_seconds=(float(_bar_age) if (candle_available and _bar_age is not None) else None),
        fallback=candle_fallback,
        note=(("Structure evidence health; exact upstream may be Finnhub, Polygon or Yahoo fallback. "
               f"fetched_at={now_iso}; last_completed_bar_end={_bar_end}; "
               f"observation_age_seconds={_bar_age}")
              if not candle_derived else
              "DERIVED: NQ structure was inferred from a single QQQ quote scalar. "
              "No candle series was requested or received."),
    )
    # V6.6.6: surface WHY the candle series was unavailable. Without this a missing
    # POLYGON_API_KEY and a rejected one are indistinguishable from this endpoint,
    # because both simply report 'derived'. Diagnostic only -- availability,
    # freshness and the fail-closed semantics above are untouched.
    _candle_failure = data.get("provider_candle_failure")
    if isinstance(_candle_failure, dict) and not candle_available:
        source_health["candles"]["failure_reason"] = _candle_failure.get("reason")
        source_health["candles"]["failure_stage"] = _candle_failure.get("stage")
        if _candle_failure.get("remediation"):
            source_health["candles"]["remediation"] = _candle_failure.get("remediation")

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
            status=_session_status("dxy", dxy_obs.age_seconds, signal is not None),
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
    # VOLATILITY / VIX CONTEXT (Phase 30 cognitive specialist)
    # ----------------------------------------------------------
    if isinstance(vix_obs, MarketObservation) and vix_obs.value is not None:
        data["vix_value"] = round(float(vix_obs.value), 4)
        data["vix_change_percent"] = (
            round(float(vix_obs.change_percent), 4)
            if vix_obs.change_percent is not None else None
        )
        # VIX is a risk-pressure input, so higher VIX maps bearish for NQ.
        value = float(vix_obs.value)
        data["vix_signal"] = 0.25 if value < 16.0 else 0.0 if value < 22.0 else -0.45 if value < 30.0 else -0.70
        data["vix_source"] = vix_obs.source
        data["vix_source_timestamp"] = vix_obs.observed_at
        source_health["volatility"] = _source_item(
            available=True, status=_session_status("volatility", vix_obs.age_seconds, True),
            source=vix_obs.source, freshness=vix_obs.freshness,
            observed_at=vix_obs.observed_at, age_seconds=vix_obs.age_seconds,
            fallback=False, value=data["vix_value"], change_percent=data["vix_change_percent"],
            note="Direct VIX context for the cognitive volatility/options specialist.",
        )
    else:
        data["vix_value"] = None
        data["vix_signal"] = None
        data["vix_source"] = "missing"
        source_health["volatility"] = _source_item(
            available=False, source="missing", freshness="missing",
            note="VIX unavailable; cognitive derivatives specialist remains missing rather than neutral.",
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
            status=_session_status("us10y", tnx_obs.age_seconds, True),
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
    # V6.6.7 NEWS AGE IS THE AGE OF THE EVIDENCE, NOT OF THE FETCH.
    # age_seconds was hardcoded 0.0, so the 12h news staleness ceiling could
    # never fire and a stale headline was indistinguishable from a breaking one.
    _news_age = data.get("news_newest_article_age_seconds")
    _news_basis = str(data.get("news_age_basis") or "UNKNOWN")
    _news_fresh = ("request_live" if not news_available
                   else ("unknown" if _news_age is None else "recent"))
    source_health["news"] = _source_item(
        available=news_available,
        source=(f"{data.get('news_provider_selected') or 'NewsAPI/Finnhub'} live-news aggregator "
                "(secondary outlets; not primary filings/wires)"),
        freshness=_news_fresh,
        # V6.6.8: a 24h-old article set is STALE, whatever the fetch said. The
        # ceiling that already excludes it from the forecast is now also what the
        # dashboard shows, so display and gate agree.
        status=("stale" if (news_available and _news_age is not None
                            and _news_age > 43200.0) else news_status),
        observed_at=(data.get("news_observed_at") or (now_iso if news_available else None)),
        age_seconds=(float(_news_age) if _news_age is not None else None),
        evidence_state=("RELEASED_VERIFIED" if news_available else "SOURCE_FAILURE"),
        note=(f"articles={data.get('news_articles', 0)}, "
              f"scored={data.get('news_scored_articles', 0)}, "
              f"age_basis={_news_basis}, "
              f"newest_age_s={_news_age}, "
              f"median_age_s={data.get('news_median_article_age_seconds')}, "
              f"oldest_age_s={data.get('news_oldest_article_age_seconds')}, "
              f"future_dated={data.get('news_future_dated_articles', 0)}, "
              f"selected_provider={data.get('news_provider_selected')}, "
              f"candidate_counts={data.get('news_provider_candidate_counts')}; "
              "PRIMARY SOURCE COVERAGE = 0 (aggregated secondary reporting); "
              "sentiment = unweighted keyword count, not a validated model"),
    )

    macro_status = str(data.get("macro_status") or "missing")
    macro_available = "missing" not in macro_status.lower() and "unavailable" not in macro_status.lower()
    # V6.6.7: macro carries the same explicit state. There is no macro EVENT
    # CALENDAR producer in this build, so the honest state is "no producer" --
    # not "the source failed" and not a silent absence.
    _m_state = ("RELEASED_VERIFIED" if macro_available
                else ("NO_PRODUCER_IMPLEMENTED"
                      if "missing_event_calendar" in macro_status.lower()
                      else "SOURCE_FAILURE"))
    source_health["macro"] = _source_item(
        evidence_state=_m_state,
        available=macro_available,
        source="FRED",
        freshness="request_live" if macro_available else "missing",
        status="live" if macro_available else "missing",
        observed_at=now_iso if macro_available else None,
        age_seconds=0.0 if macro_available else None,
        note=macro_status,
    )

    earnings_calendar_available = bool(data.get("earnings_calendar_available"))
    earnings_directional_available = data.get("earnings") is not None
    source_health["earnings_calendar"] = _source_item(
        available=earnings_calendar_available,
        source="Finnhub earnings calendar",
        freshness="request_live" if earnings_calendar_available else "missing",
        status="live" if earnings_calendar_available else "missing",
        observed_at=now_iso if earnings_calendar_available else None,
        age_seconds=0.0 if earnings_calendar_available else None,
        note=f"tracked_events={data.get('earnings_events', 0)}; status={data.get('earnings_status') or 'unknown'}",
    )
    # Legacy `earnings` health means directional surprise evidence, not merely
    # that a future calendar event exists. Upcoming-only events stay MISSING.
    # V6.6.7 NO AMBIGUOUS MIDDLE STATE.
    # `status` previously collapsed four genuinely different situations into the
    # single word "missing": there was no relevant event, the provider failed,
    # an event is scheduled but has not reported yet, or a real surprise exists.
    # Those demand different reactions, so they are now separate states. The
    # score is unchanged either way -- this is provenance, not a new input.
    _e_raw = str(data.get("earnings_status") or "unknown")
    _EARNINGS_STATE = {
        "released_surprise": "RELEASED_VERIFIED",
        "upcoming_only_no_released_surprise": "UPCOMING_VERIFIED_NO_SURPRISE_YET",
        "no_tracked_events": "NO_RELEVANT_EVENT",
        "provider_error": "SOURCE_FAILURE",
    }
    _e_state = _EARNINGS_STATE.get(_e_raw, "DATA_MISSING_UNCLASSIFIED")
    _e_status = {
        "RELEASED_VERIFIED": "live",
        "UPCOMING_VERIFIED_NO_SURPRISE_YET": "no_directional_evidence",
        "NO_RELEVANT_EVENT": "not_applicable",
        "SOURCE_FAILURE": "provider_error",
    }.get(_e_state, "missing")
    source_health["earnings"] = _source_item(
        available=earnings_directional_available,
        source="Released earnings surprise evidence",
        freshness="request_live" if earnings_directional_available else "missing",
        status=_e_status,
        evidence_state=_e_state,
        observed_at=now_iso if earnings_directional_available else None,
        age_seconds=0.0 if earnings_directional_available else None,
        note=(f"calendar_available={earnings_calendar_available}; directional_surprise_available={earnings_directional_available}; "
              f"status={data.get('earnings_status') or 'unknown'}"),
    )

    liquidity_available = bool(data.get("liquidity_evidence_available"))
    liquidity_evidence = data.get("liquidity_evidence") or {}
    nq_liquidity = data.get("nq_liquidity") or {}
    liquidity_quality = str(nq_liquidity.get("source_quality") or
                            liquidity_evidence.get("source_quality") or "UNKNOWN")
    liquidity_proxy = bool(liquidity_evidence.get("is_proxy")) or (
        "PROXY" in liquidity_quality.upper() or
        "CONTINUOUS" in liquidity_quality.upper())
    liquidity_fallback = liquidity_available and (
        liquidity_proxy or "FALLBACK" in liquidity_quality.upper())
    source_health["liquidity"] = _source_item(
        available=liquidity_available,
        source=str(nq_liquidity.get("source") or "QQQ period candles + NQ futures session candles"),
        fallback=liquidity_fallback,
        freshness="request_live" if liquidity_available else "missing",
        observed_at=now_iso if liquidity_available else None,
        age_seconds=0.0 if liquidity_available else None,
        note=str(data.get("liquidity_evidence") or {}),
    )
    source_health["liquidity"]["source_quality"] = liquidity_quality
    source_health["liquidity"]["is_proxy"] = liquidity_proxy

    data["source_health"] = source_health
    data["provider_health"] = build_provider_health(source_health)
    data["provider_health_status"] = data["provider_health"]["overall"]
    data["provider_health_score"] = data["provider_health"]["score"]
    return data
