"""Live market-truth enrichment for CLEAR NASDAQ FIA.

Purpose
-------
Replace two known proxy inputs when genuine direct observations are available,
and fill the missing point-in-time macro-calendar producer without inventing
neutral/directional evidence.  Earnings/guidance provenance is strengthened with
SEC verification when a relevant tracked event exists.

Scientific rules
----------------
* Never backfill a missed Forward-OOS checkpoint.
* Never turn missing data into a numeric zero.
* Direct NQ structure requires an explicit quarterly NQ contract.
* Direct SPX confirmation requires a fresh ^GSPC observation; otherwise the
  existing explicitly-labelled SPY fallback remains untouched.
* Macro gets a numeric vote only when a released tracked event has actual and
  consensus values and the pre-existing Phase34 event-semantics map can score it.
* A live calendar with no released surprise is evidence availability, not a
  directional vote.
* SEC filings prove primary-source filing context; they are NOT automatically
  interpreted as bullish/bearish guidance.

This module intentionally changes no FIA weights, probability mapping, decision
thresholds, risk logic, or Forward-OOS ledger rules.
"""
from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

UTC = timezone.utc
_PATCH_TTL_SECONDS = 60.0
_TRACKED = {
    "NVDA", "MSFT", "AAPL", "AMZN", "META", "AVGO", "GOOGL", "GOOG",
    "TSLA", "NFLX", "AMD", "MU", "INTC", "QCOM", "SMCI",
}


def _finite(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = value.strip().replace(",", "").replace("%", "")
        out = float(value)
        return out if math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def _iso_from_ts(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), UTC).isoformat()


def _completed_structure_from_candles(candles: Dict[str, Any], bar_seconds: int = 3600) -> Optional[Dict[str, Any]]:
    now = int(time.time())
    closes = list((candles or {}).get("c") or [])
    stamps = list((candles or {}).get("t") or [])
    if len(closes) != len(stamps):
        return None

    completed = []
    for close, stamp in zip(closes, stamps):
        c = _finite(close)
        try:
            t = int(stamp)
        except (TypeError, ValueError, OverflowError):
            continue
        if c is None or t + bar_seconds > now:
            continue
        completed.append((c, t))

    if len(completed) < 10:
        return None

    values = [x[0] for x in completed]
    stamps = [x[1] for x in completed]
    last = values[-1]
    window = values[-40:]
    hi, lo = max(window), min(window)
    position = 0.0 if hi <= lo else ((last - lo) / (hi - lo)) * 2.0 - 1.0
    ref = values[-7] if len(values) >= 7 else values[0]
    momentum = 0.0 if ref == 0 else max(-1.0, min(1.0, ((last - ref) / ref) * 100.0))
    score = max(-1.0, min(1.0, 0.5 * position + 0.5 * momentum))
    return {
        "score": round(score, 6),
        "completed_bars": len(values),
        "last_completed_bar_start_utc": _iso_from_ts(stamps[-1]),
        "last_completed_bar_end_utc": _iso_from_ts(stamps[-1] + bar_seconds),
        "range_position": round(position, 6),
        "momentum": round(momentum, 6),
    }


async def _direct_nq_structure(hub: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    nq = data.get("nq_liquidity") if isinstance(data.get("nq_liquidity"), dict) else {}
    contract = str(nq.get("symbol") or "").upper()
    quality = str(nq.get("source_quality") or "").upper()
    if quality != "EXPLICIT_CONTRACT" or not contract.startswith("NQ"):
        return {"nq_truth_status": "DIRECT_EXPLICIT_CONTRACT_UNAVAILABLE"}

    now = int(time.time())
    candles = await hub.polygon_futures_candles(
        contract,
        multiplier=1,
        timespan="hour",
        start_ts=now - 12 * 86400,
        end_ts=now,
    )
    structure = _completed_structure_from_candles(candles or {}, 3600)
    if not structure:
        return {"nq_truth_status": "DIRECT_EXPLICIT_CONTRACT_CANDLES_UNAVAILABLE"}

    source = f"Massive Futures v1 explicit NQ contract {contract} 1h completed bars"
    return {
        "nq_truth_status": "DIRECT_EXPLICIT_CONTRACT",
        "nq_structure": structure["score"],
        "provider_candle_evidence": "available",
        "nq_structure_basis": f"{contract}_60M_EXPLICIT_CONTRACT_COMPLETED_BARS",
        "nq_structure_bars": structure["completed_bars"],
        "nq_structure_last_bar_end_utc": structure["last_completed_bar_end_utc"],
        "nq_structure_source": source,
        "nq_structure_instrument": "NQ",
        "nq_structure_contract": contract,
        "nq_structure_is_proxy": False,
        "nq_structure_detail": (
            f"DIRECT NQ: {contract}; {structure['completed_bars']} completed 60m bars; "
            f"range position {structure['range_position']:+.3f}, "
            f"momentum {structure['momentum']:+.3f}; forming bar excluded"
        ),
    }


async def _direct_spx_confirmation(hub: Any) -> Dict[str, Any]:
    # Reuse the project's existing keyless Yahoo observation path, but query the
    # index itself (^GSPC), not SPY.  Fail closed if the index print is too old.
    try:
        from .provider_reliability import yahoo_observation
        obs = await yahoo_observation("^GSPC")
    except Exception:
        obs = None

    if obs is None or getattr(obs, "value", None) is None:
        return {"spx_truth_status": "DIRECT_SPX_UNAVAILABLE"}

    age = getattr(obs, "age_seconds", None)
    if age is None or float(age) > 20 * 60:
        return {
            "spx_truth_status": "DIRECT_SPX_STALE",
            "spx_direct_age_seconds": age,
            "spx_direct_observed_at": getattr(obs, "observed_at", None),
        }

    change = getattr(obs, "change_percent", None)
    signal = hub.normalize_change(change)
    if signal is None:
        return {"spx_truth_status": "DIRECT_SPX_NO_CHANGE_VALUE"}

    return {
        "spx_truth_status": "DIRECT_SPX_INDEX",
        "spx_confirmation": signal,
        "spx_change_percent": change,
        "spx_price": float(obs.value),
        "spx_source": "Yahoo Finance ^GSPC direct S&P 500 index",
        "spx_source_timestamp": getattr(obs, "observed_at", None),
        "spx_source_age_seconds": age,
        "spx_confirmation_is_proxy": False,
    }


def _macro_type(name: str) -> Optional[str]:
    text = str(name or "").lower()
    if "core" in text and ("consumer price" in text or "cpi" in text):
        return "CORE_CPI"
    if "consumer price" in text or "cpi" in text:
        return "CPI"
    if "core" in text and ("personal consumption" in text or "pce" in text):
        return "CORE_PCE"
    if "personal consumption" in text or "pce" in text:
        return "PCE"
    if "nonfarm" in text or "non-farm" in text or "payroll" in text:
        return "NFP"
    if "unemployment rate" in text:
        return "UNEMPLOYMENT"
    if "gross domestic product" in text or "gdp" in text:
        return "GDP"
    if "ism" in text or "pmi" in text:
        return "ISM"
    return None


def _event_name(row: Dict[str, Any]) -> str:
    return str(row.get("event") or row.get("name") or row.get("indicator") or row.get("title") or "").strip()


def _event_dt(row: Dict[str, Any]) -> Optional[datetime]:
    candidates = [row.get("time"), row.get("datetime"), row.get("date")]
    for value in candidates:
        if value in (None, ""):
            continue
        try:
            text = str(value).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except (ValueError, TypeError):
            pass
    return None


def _country_us(row: Dict[str, Any]) -> bool:
    country = str(row.get("country") or row.get("countryCode") or row.get("region") or "").strip().upper()
    return country in {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"} or not country


def _clean_macro_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict) or not _country_us(row):
        return None
    name = _event_name(row)
    kind = _macro_type(name)
    # FOMC/rate-decision rows are retained as catalyst risk even when the simple
    # Phase34 surprise scorer has no directional mapping for them.
    lower = name.lower()
    is_fed = any(x in lower for x in ("fomc", "federal reserve", "fed interest rate", "rate decision"))
    if not kind and not is_fed:
        return None
    actual = row.get("actual")
    estimate = row.get("estimate", row.get("consensus", row.get("forecast")))
    dt = _event_dt(row)
    return {
        "type": kind or "FOMC",
        "name": name,
        "actual": actual,
        "expected": estimate,
        "previous": row.get("prev", row.get("previous")),
        "unit": row.get("unit"),
        "time_utc": dt.isoformat() if dt else None,
        "source": "Finnhub economic calendar",
    }


async def _macro_calendar(hub: Any) -> Dict[str, Any]:
    key = str((getattr(hub, "keys", {}) or {}).get("FINNHUB_API_KEY") or "")
    if not key:
        return {"macro_calendar_available": False, "macro_status": "missing_event_calendar_no_key"}

    now = datetime.now(UTC)
    start = (now - timedelta(days=1)).date().isoformat()
    end = (now + timedelta(days=7)).date().isoformat()
    payload = await hub.get(
        "https://finnhub.io/api/v1/calendar/economic",
        {"from": start, "to": end, "token": key},
        timeout=15,
    )
    if not isinstance(payload, dict):
        return {"macro_calendar_available": False, "macro_status": "event_calendar_provider_error"}

    rows = payload.get("economicCalendar") or payload.get("economicData") or payload.get("data") or []
    cleaned = []
    for row in rows if isinstance(rows, list) else []:
        item = _clean_macro_row(row)
        if item:
            cleaned.append(item)

    cleaned.sort(key=lambda x: x.get("time_utc") or "")
    released = []
    upcoming = []
    for item in cleaned:
        dt = None
        try:
            if item.get("time_utc"):
                dt = datetime.fromisoformat(str(item["time_utc"]).replace("Z", "+00:00"))
        except ValueError:
            dt = None
        if dt is not None and dt <= now and item.get("actual") not in (None, ""):
            released.append(item)
        elif dt is None or dt > now:
            upcoming.append(item)

    out: Dict[str, Any] = {
        "macro_calendar_available": True,
        "macro_calendar_source": "Finnhub economic calendar",
        "macro_calendar_checked_at_utc": now.isoformat(),
        "macro_calendar_events": cleaned[:25],
        "macro_calendar_event_count": len(cleaned),
        "macro_upcoming_event_count": len(upcoming),
        "macro_released_event_count": len(released),
        "macro": None,
        "macro_status": "calendar_live_no_released_directional_surprise",
    }

    scoreable = [x for x in released if x.get("type") not in {None, "FOMC"}
                 and _finite(x.get("actual")) is not None and _finite(x.get("expected")) is not None]
    if scoreable:
        event = scoreable[-1]
        normalized = dict(event)
        normalized["actual"] = _finite(event.get("actual"))
        normalized["expected"] = _finite(event.get("expected"))
        out["macro_event"] = normalized
        try:
            from .phase34_event_surprise import analyze_event_surprise
            scored = analyze_event_surprise({"data": {"macro_event": normalized}})
        except Exception:
            scored = {"status": "SCORER_ERROR", "score": None}
        out["macro_event_surprise"] = scored
        score = scored.get("nasdaq_directional_score") if isinstance(scored, dict) else None
        if score is None and isinstance(scored, dict):
            score = scored.get("score")
        if score is not None:
            out["macro"] = float(score)
            out["macro_status"] = "released_surprise"
    elif upcoming:
        out["macro_status"] = "calendar_live_upcoming_only_no_directional_vote"
    return out


async def _earnings_primary_truth(hub: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    # The current build already has a real Finnhub earnings calendar.  A day with
    # zero tracked events is NOT a provider failure, so preserve that distinction.
    if not bool(data.get("earnings_calendar_available")):
        return {"earnings_primary_evidence_status": "CALENDAR_PROVIDER_UNAVAILABLE"}
    if int(data.get("earnings_events") or 0) <= 0:
        return {
            "earnings_primary_evidence_status": "NO_RELEVANT_EVENT",
            "guidance_primary_evidence_status": "NO_RELEVANT_EVENT",
            "earnings_provider_truth": "Finnhub earnings calendar available; zero tracked events",
        }

    key = str((getattr(hub, "keys", {}) or {}).get("FINNHUB_API_KEY") or "")
    if not key:
        return {"earnings_primary_evidence_status": "CALENDAR_KEY_UNAVAILABLE"}

    now = datetime.now(UTC)
    payload = await hub.get(
        "https://finnhub.io/api/v1/calendar/earnings",
        {
            "from": (now - timedelta(days=1)).date().isoformat(),
            "to": (now + timedelta(days=7)).date().isoformat(),
            "token": key,
        },
        timeout=15,
    )
    events = (payload or {}).get("earningsCalendar", []) if isinstance(payload, dict) else []
    tracked = [e for e in events if isinstance(e, dict) and str(e.get("symbol") or "").upper() in _TRACKED]
    symbols = sorted({str(e.get("symbol") or "").upper() for e in tracked})[:6]
    cleaned = [{
        "symbol": str(e.get("symbol") or "").upper(),
        "date": e.get("date"),
        "hour": e.get("hour"),
        "epsActual": e.get("epsActual"),
        "epsEstimate": e.get("epsEstimate"),
        "revenueActual": e.get("revenueActual"),
        "revenueEstimate": e.get("revenueEstimate"),
    } for e in tracked]

    result: Dict[str, Any] = {
        "earnings_calendar_events_verified": cleaned[:20],
        "earnings_primary_evidence_status": "CALENDAR_VERIFIED",
        "guidance_primary_evidence_status": "NOT_DIRECTIONALLY_PARSED",
    }
    if symbols:
        try:
            from .cognitive.official_sources import verify_primary_event
            sec = await verify_primary_event(symbols, now)
        except Exception:
            sec = {"provider": "SEC EDGAR", "verified_symbols": [], "status": "ERROR"}
        result["earnings_sec_verification"] = sec
        verified = list((sec or {}).get("verified_symbols") or [])
        if verified:
            result["earnings_primary_evidence_status"] = "SEC_PRIMARY_FILING_VERIFIED"
            result["earnings_source"] = "Finnhub earnings calendar + SEC EDGAR"
            result["guidance_primary_evidence_status"] = "PRIMARY_FILING_PRESENT_NOT_DIRECTIONALLY_PARSED"
    return result


def _apply_source_health(data: Dict[str, Any]) -> None:
    source_health = data.get("source_health") if isinstance(data.get("source_health"), dict) else {}
    source_health = dict(source_health)
    now = datetime.now(UTC)

    if data.get("nq_truth_status") == "DIRECT_EXPLICIT_CONTRACT":
        bar_end = data.get("nq_structure_last_bar_end_utc")
        age = None
        try:
            dt = datetime.fromisoformat(str(bar_end).replace("Z", "+00:00"))
            age = max(0.0, (now - dt.astimezone(UTC)).total_seconds())
        except Exception:
            pass
        source_health["candles"] = {
            "available": True,
            "status": "live" if age is not None and age <= 20 * 60 else "recent",
            "source": data.get("nq_structure_source"),
            "freshness": "live" if age is not None and age <= 20 * 60 else "recent",
            "observed_at": bar_end,
            "age_seconds": round(age, 1) if age is not None else None,
            "fallback": False,
            "value": data.get("nq_structure"),
            "change_percent": None,
            "note": data.get("nq_structure_detail"),
            "evidence_state": "DIRECT_EXPLICIT_CONTRACT",
        }

    if data.get("spx_truth_status") == "DIRECT_SPX_INDEX":
        source_health["spx_confirmation"] = {
            "available": True,
            "status": "live",
            "source": data.get("spx_source"),
            "freshness": "live",
            "observed_at": data.get("spx_source_timestamp"),
            "age_seconds": data.get("spx_source_age_seconds"),
            "fallback": False,
            "value": data.get("spx_price"),
            "change_percent": data.get("spx_change_percent"),
            "note": "Direct S&P 500 index confirmation; SPY proxy replaced for this snapshot.",
            "evidence_state": "DIRECT_INDEX",
        }

    if data.get("macro_calendar_available"):
        source_health["macro"] = {
            "available": True,
            "status": "live",
            "source": data.get("macro_calendar_source"),
            "freshness": "request_live",
            "observed_at": data.get("macro_calendar_checked_at_utc"),
            "age_seconds": 0.0,
            "fallback": False,
            "value": data.get("macro"),
            "change_percent": None,
            "note": data.get("macro_status"),
            "evidence_state": ("RELEASED_VERIFIED" if data.get("macro") is not None else "CALENDAR_VERIFIED_NO_DIRECTIONAL_VOTE"),
        }

    if data.get("earnings_primary_evidence_status"):
        cal = source_health.get("earnings_calendar") if isinstance(source_health.get("earnings_calendar"), dict) else {}
        if cal:
            cal = dict(cal)
            cal["primary_verification"] = data.get("earnings_primary_evidence_status")
            cal["guidance_verification"] = data.get("guidance_primary_evidence_status")
            if data.get("earnings_source"):
                cal["source"] = data.get("earnings_source")
            source_health["earnings_calendar"] = cal
        earn = source_health.get("earnings") if isinstance(source_health.get("earnings"), dict) else {}
        if earn:
            earn = dict(earn)
            earn["primary_verification"] = data.get("earnings_primary_evidence_status")
            earn["guidance_verification"] = data.get("guidance_primary_evidence_status")
            if data.get("earnings_source"):
                earn["source"] = data.get("earnings_source")
            source_health["earnings"] = earn

    data["source_health"] = source_health
    try:
        from .provider_reliability import build_provider_health
        data["provider_health"] = build_provider_health(source_health)
        data["provider_health_status"] = data["provider_health"].get("overall")
    except Exception:
        pass


async def _build_patch(hub: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    nq_task = _direct_nq_structure(hub, data)
    spx_task = _direct_spx_confirmation(hub)
    macro_task = _macro_calendar(hub)
    earnings_task = _earnings_primary_truth(hub, data)
    results = await asyncio.gather(nq_task, spx_task, macro_task, earnings_task, return_exceptions=True)
    patch: Dict[str, Any] = {}
    labels = ("nq", "spx", "macro", "earnings")
    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            patch[f"{label}_truth_error"] = type(result).__name__
        elif isinstance(result, dict):
            patch.update(result)
    patch["live_market_truth_checked_at_utc"] = datetime.now(UTC).isoformat()
    patch["live_market_truth_policy"] = "DIRECT_WHEN_VERIFIED_FAIL_CLOSED_NO_FAKE_ZERO"
    return patch


def _replace_provenance_text(text: str, data: Dict[str, Any]) -> str:
    out = str(text or "")
    if data.get("nq_truth_status") == "DIRECT_EXPLICIT_CONTRACT":
        out = out.replace(
            "PROXY: QQQ 60m completed-bar structure. NOT NQ futures.",
            str(data.get("nq_structure_detail") or "DIRECT NQ explicit-contract completed-bar structure."),
        )
    if data.get("spx_truth_status") == "DIRECT_SPX_INDEX":
        out = out.replace(
            "PROXY: SPY normalised percent change. NOT an SPX divergence statistic.",
            "DIRECT SPX: ^GSPC normalised percent change from a fresh S&P 500 index observation.",
        )
    return out


def install() -> None:
    """Patch ProviderHub.snapshot and engine.build_forecast once, without I/O."""
    from .providers import ProviderHub
    from . import engine as engine_module

    if getattr(ProviderHub, "_live_market_truth_installed", False):
        return

    original_snapshot = ProviderHub.snapshot
    original_build_forecast = engine_module.build_forecast

    async def snapshot_with_truth(self: Any):
        result = await original_snapshot(self)
        if not isinstance(result, dict):
            return result
        data = result.get("data") if isinstance(result.get("data"), dict) else None
        if data is None:
            return result

        now_mono = time.monotonic()
        cached = getattr(self, "_live_market_truth_patch_cache", None)
        cached_at = float(getattr(self, "_live_market_truth_patch_cache_time", 0.0) or 0.0)
        if not isinstance(cached, dict) or now_mono - cached_at >= _PATCH_TTL_SECONDS:
            cached = await _build_patch(self, data)
            self._live_market_truth_patch_cache = dict(cached)
            self._live_market_truth_patch_cache_time = time.monotonic()

        data.update(cached)
        _apply_source_health(data)
        overall = str((data.get("provider_health") or {}).get("overall") or result.get("status") or "DEGRADED").upper()
        if overall in {"LIVE", "DEGRADED", "ERROR"}:
            result["status"] = overall
        # Original snapshot cache points at this same result object; preserving it
        # means all readers in the next 8 seconds see identical enriched evidence.
        return result

    def build_forecast_with_truth(snapshot: Dict[str, Any]):
        forecast = original_build_forecast(snapshot)
        raw = snapshot.get("data", {}) if isinstance(snapshot, dict) else {}
        if not isinstance(raw, dict):
            return forecast

        for signal in getattr(forecast, "signals", []) or []:
            if getattr(signal, "name", "") == "NQ structure" and raw.get("nq_truth_status") == "DIRECT_EXPLICIT_CONTRACT":
                signal.detail = str(raw.get("nq_structure_detail") or signal.detail)
            elif getattr(signal, "name", "") == "SPX confirmation" and raw.get("spx_truth_status") == "DIRECT_SPX_INDEX":
                signal.detail = "DIRECT SPX: ^GSPC normalised percent change; fresh direct index observation."
            elif getattr(signal, "name", "") == "Macro calendar" and raw.get("macro") is not None:
                ev = raw.get("macro_event") or {}
                signal.detail = f"Released macro surprise via Finnhub calendar: {ev.get('name') or ev.get('type') or 'tracked event'}"
            elif getattr(signal, "name", "") == "Earnings/guidance" and raw.get("earnings_source"):
                signal.detail = "Earnings impulse with SEC primary-filing provenance; guidance direction is not inferred from filing presence alone."

        if hasattr(forecast, "thesis"):
            forecast.thesis = _replace_provenance_text(forecast.thesis, raw)
        if hasattr(forecast, "bullish_evidence"):
            forecast.bullish_evidence = [_replace_provenance_text(x, raw) for x in (forecast.bullish_evidence or [])]
        if hasattr(forecast, "bearish_evidence"):
            forecast.bearish_evidence = [_replace_provenance_text(x, raw) for x in (forecast.bearish_evidence or [])]
        if isinstance(getattr(forecast, "source_status", None), dict):
            forecast.source_status["nq_structure"] = str(raw.get("nq_truth_status") or "LEGACY")
            forecast.source_status["spx_confirmation"] = str(raw.get("spx_truth_status") or "LEGACY")
            forecast.source_status["macro_calendar"] = str(raw.get("macro_status") or "unknown")
            forecast.source_status["earnings_primary"] = str(raw.get("earnings_primary_evidence_status") or "unknown")
        return forecast

    ProviderHub.snapshot = snapshot_with_truth
    engine_module.build_forecast = build_forecast_with_truth
    ProviderHub._live_market_truth_installed = True
