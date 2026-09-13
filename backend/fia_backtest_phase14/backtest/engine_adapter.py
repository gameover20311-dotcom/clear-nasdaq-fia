import os
from pathlib import Path
from typing import Any, Dict, Optional

from .recorder import build_prediction_record, append_prediction


_PROTECTED_HISTORICAL_SUFFIX = (
    "fia_backtest_phase14",
    "data",
    "historical_predictions.csv",
)


def _protected_historical_target(output_path) -> bool:
    """Return True only for the sealed phase14 historical CSV.

    Production used to append to this file from /api/forecast, which changed a
    protected artifact merely by reading the live dashboard.  Backtest/research
    tooling may still write to explicit disposable paths.  Updating the sealed
    historical CSV itself now requires a deliberate one-shot opt-in and must
    never happen through a normal service request.
    """
    try:
        parts = Path(output_path).as_posix().rstrip("/").split("/")
    except Exception:
        return False
    return tuple(parts[-3:]) == _PROTECTED_HISTORICAL_SUFFIX


def record_fia_forecast(
    forecast: Any,
    entry_price: Optional[float],
    output_path,
) -> Dict[str, Any]:
    """
    Convert an existing FIA Forecast object into the standardized
    historical recorder format.

    This adapter does NOT modify the forecast or FIA calculations.

    Scientific-integrity boundary: the production service must not mutate the
    sealed phase14 historical_predictions.csv.  A dedicated offline migration
    may opt in with FIA_ALLOW_PROTECTED_HISTORICAL_APPEND=1, but ordinary live
    requests fail closed and leave the artifact byte-identical.
    """

    payload = {
        "symbol": getattr(forecast, "symbol", None),
        "horizon_hours": getattr(forecast, "horizon_hours", None),
        "direction": getattr(forecast, "direction", None),
        "bullish_probability": getattr(
            forecast,
            "bullish_probability",
            None,
        ),
        "bearish_probability": getattr(
            forecast,
            "bearish_probability",
            None,
        ),
        "confidence": getattr(
            forecast,
            "confidence",
            None,
        ),
    }

    generated_at = getattr(
        forecast,
        "generated_at",
        None,
    )

    record = build_prediction_record(
        payload,
        entry_price=entry_price,
        timestamp=generated_at,
    )

    if _protected_historical_target(output_path):
        allowed = str(os.getenv("FIA_ALLOW_PROTECTED_HISTORICAL_APPEND", "0") or "0").strip().lower()
        if allowed not in {"1", "true", "yes", "on"}:
            return {
                "record": record,
                "output_path": str(output_path),
                "ready": False,
                "blocked": True,
                "reason": "PROTECTED_HISTORICAL_ARTIFACT_READ_ONLY",
            }

    append_prediction(
        output_path,
        record,
    )

    return {
        "record": record,
        "output_path": str(output_path),
        "ready": True,
    }
