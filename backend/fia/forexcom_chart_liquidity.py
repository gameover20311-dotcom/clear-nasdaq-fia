from __future__ import annotations
import json, math, os, time
from pathlib import Path
from typing import Any, Dict, Optional

CHART_SYMBOL = "FOREXCOM:NAS100"
STORE = Path(__file__).resolve().parents[1] / "fia_chart_sync" / "forexcom_nas100_latest.json"
MAX_AGE_SECONDS = int(os.getenv("FIA_FOREXCOM_CHART_SYNC_MAX_AGE_SECONDS", "1800"))
TOKEN = os.getenv("FIA_CHART_SYNC_TOKEN", "").strip()

PRIMARY_KEYS = (
    "monthly_high","monthly_low","weekly_high","weekly_low","daily_high","daily_low",
    "asia_high","asia_low","london_high","london_low",
    "new_york_high","new_york_low","london_close_high","london_close_low",
)

def _finite(value: Any) -> Optional[float]:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def _chart_tick(value: Any) -> Optional[float]:
    x = _finite(value)
    return None if x is None else round(x, 1)

def _epoch_seconds(value: Any) -> Optional[float]:
    x = _finite(value)
    if x is None:
        return None
    return x / 1000.0 if x > 10_000_000_000 else x

def validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object")
    symbol = str(payload.get("symbol") or "").upper().strip()
    if symbol != CHART_SYMBOL:
        raise ValueError(f"Expected symbol {CHART_SYMBOL}, got {symbol or 'MISSING'}")
    if TOKEN and str(payload.get("token") or "") != TOKEN:
        raise PermissionError("Invalid FIA_CHART_SYNC_TOKEN")

    ts = _epoch_seconds(payload.get("timestamp")) or time.time()
    raw = payload.get("levels") or {}
    if not isinstance(raw, dict):
        raise ValueError("levels must be an object")

    levels = {k: _chart_tick(raw.get(k)) for k in PRIMARY_KEYS if k in raw}
    prev = payload.get("previous_completed") or {}
    previous = {}
    if isinstance(prev, dict):
        previous = {str(k): _chart_tick(v) for k, v in prev.items()}

    return {
        "symbol": CHART_SYMBOL,
        "provider": "FOREX.com via TradingView chart-sync",
        "timestamp": ts,
        "received_at": time.time(),
        "current_price": _chart_tick(payload.get("current_price")),
        "levels": levels,
        "previous_completed": previous,
        "chart_timeframe": str(payload.get("chart_timeframe") or "15"),
        "chart_timezone": str(payload.get("chart_timezone") or "America/New_York"),
        "session_windows": payload.get("session_windows") or {},
        "source_truth": "EXACT_USER_CHART_FEED",
    }

def save_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    clean = validate_payload(payload)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STORE)
    return clean

def load_latest() -> Dict[str, Any]:
    if not STORE.exists():
        return {"status": "MISSING", "symbol": CHART_SYMBOL}
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "ERROR", "symbol": CHART_SYMBOL, "error": str(exc)}
    received = _finite(data.get("received_at"))
    age = None if received is None else max(0.0, time.time() - received)
    data["age_seconds"] = None if age is None else round(age, 1)
    data["status"] = "LIVE" if age is not None and age <= MAX_AGE_SECONDS else "STALE"
    return data

async def apply_forexcom_chart_liquidity(hub: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    latest = load_latest()
    existing_nq = data.get("nq_liquidity")
    if existing_nq:
        data["nq_reference_liquidity"] = existing_nq

    if latest.get("status") != "LIVE":
        for key in PRIMARY_KEYS:
            data.pop(key, None)
        data["nq_liquidity"] = {
            "instrument": "NAS100",
            "symbol": CHART_SYMBOL,
            "current_price": None,
            "levels": {},
            "source": "TradingView FOREXCOM:NAS100 chart sync missing/stale",
            "primary_chart_liquidity": True,
            "status": latest.get("status"),
        }
        data["liquidity_primary_instrument"] = CHART_SYMBOL
        data["liquidity_evidence_available"] = False
        data["liquidity_evidence"] = {
            "chart_forexcom_nas100": latest.get("status", "MISSING"),
            "nq_futures_reference": "available" if existing_nq else "missing",
        }
        data["liquidity_truth_fix"] = {
            "status": "WAITING_FOR_EXACT_CHART_SYNC",
            "primary_symbol": CHART_SYMBOL,
            "wrong_scale_fallback_blocked": True,
        }
        return data

    levels = {
        k: v for k, v in (latest.get("levels") or {}).items()
        if k in PRIMARY_KEYS and _finite(v) is not None
    }
    for key, value in levels.items():
        data[key] = value

    chart_meta = {
        "instrument": "NAS100",
        "symbol": CHART_SYMBOL,
        "current_price": latest.get("current_price"),
        "levels": levels,
        "source": latest.get("provider"),
        "primary_chart_liquidity": True,
        "status": "LIVE",
        "chart_timeframe": latest.get("chart_timeframe"),
        "chart_timezone": latest.get("chart_timezone"),
        "session_windows": latest.get("session_windows"),
        "previous_completed": latest.get("previous_completed"),
        "age_seconds": latest.get("age_seconds"),
        "tick_size": 0.1,
    }
    data["nq_liquidity"] = chart_meta
    data["forexcom_nas100_liquidity"] = chart_meta
    data["liquidity_primary_instrument"] = CHART_SYMBOL
    data["liquidity_evidence_available"] = bool(levels)
    data["liquidity_evidence"] = {
        "chart_forexcom_nas100": "available" if levels else "partial",
        "nq_futures_reference": "available" if existing_nq else "missing",
    }
    data["liquidity_truth_fix"] = {
        "status": "ACTIVE_EXACT_CHART_FEED",
        "primary_symbol": CHART_SYMBOL,
        "source": "TradingView chart alert/webhook",
        "wrong_scale_fallback_blocked": True,
        "nq_futures_price_overwritten": False,
    }
    return data
