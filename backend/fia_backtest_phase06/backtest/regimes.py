from typing import Any, Dict, Optional


def _num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_regime(
    *,
    trend_score: Any = None,
    volatility: Any = None,
    market_regime: Optional[str] = None,
) -> str:
    """
    Classify a historical observation without changing FIA's live regime.

    Priority:
    1. Explicit FIA regime when available.
    2. Trend/volatility classification when numerical inputs exist.
    3. UNKNOWN when the required evidence is unavailable.
    """
    if market_regime:
        value = str(market_regime).strip()
        if value:
            return value.upper()

    trend = _num(trend_score)
    vol = _num(volatility)

    if trend is None and vol is None:
        return "UNKNOWN"

    if trend is not None:
        if trend >= 0.5:
            trend_label = "TREND_UP"
        elif trend <= -0.5:
            trend_label = "TREND_DOWN"
        else:
            trend_label = "TREND_NEUTRAL"
    else:
        trend_label = "TREND_UNKNOWN"

    if vol is not None:
        vol_label = "HIGH_VOL" if vol >= 0.02 else "LOW_VOL"
    else:
        vol_label = "VOL_UNKNOWN"

    return f"{trend_label}|{vol_label}"


def classify_from_forecast(forecast: Dict[str, Any]) -> str:
    """
    Extract the existing FIA regime when available.
    Does not alter or recalculate the live FIA forecast.
    """
    return classify_regime(
        market_regime=forecast.get("regime"),
        trend_score=forecast.get("trend_score"),
        volatility=forecast.get("volatility"),
    )
