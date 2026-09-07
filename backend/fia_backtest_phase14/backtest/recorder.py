import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


FIELDS = [
    "prediction_id",
    "timestamp",
    "horizon",
    "symbol",
    "direction",
    "bullish_probability",
    "bearish_probability",
    "confidence",
    "entry_price",
    "future_price",
    "return_pct",
    "outcome_direction",
    "correct",
    "mfe_pct",
    "mae_pct",
]


def _value(payload: Dict[str, Any], *keys):
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def build_prediction_record(
    forecast: Dict[str, Any],
    entry_price: Optional[float],
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:

    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    prediction_id = (
        f"NQ-{timestamp.replace(':', '').replace('+00:00', 'Z')}"
    )

    return {
        "prediction_id": prediction_id,
        "timestamp": timestamp,
        "horizon": _value(
            forecast,
            "horizon",
            "horizon_hours",
        ),
        "symbol": _value(
            forecast,
            "symbol",
        ) or "NQ",
        "direction": _value(
            forecast,
            "direction",
        ),
        "bullish_probability": _value(
            forecast,
            "bullish_probability",
            "bullish_probability_pct",
        ),
        "bearish_probability": _value(
            forecast,
            "bearish_probability",
            "bearish_probability_pct",
        ),
        "confidence": _value(
            forecast,
            "confidence",
        ),
        "entry_price": entry_price,
        "future_price": None,
        "return_pct": None,
        "outcome_direction": None,
        "correct": None,
        "mfe_pct": None,
        "mae_pct": None,
    }


def append_prediction(
    path: str,
    record: Dict[str, Any],
) -> Path:

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    exists = path.exists() and path.stat().st_size > 0

    with path.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=FIELDS,
            extrasaction="ignore",
        )

        if not exists:
            writer.writeheader()

        writer.writerow(record)

    return path

def resolve_prediction_outcome(
    entry_price: float,
    future_price: float,
    direction: str,
    high_price: Optional[float] = None,
    low_price: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Resolve a completed FIA prediction without changing FIA forecast logic.

    Returns the realized return, outcome direction, correctness,
    and MFE/MAE percentages relative to the entry price.
    """

    entry = float(entry_price)
    future = float(future_price)

    if entry <= 0:
        raise ValueError("entry_price must be greater than zero")

    move_pct = ((future - entry) / entry) * 100.0

    if future > entry:
        outcome_direction = "BULLISH"
    elif future < entry:
        outcome_direction = "BEARISH"
    else:
        outcome_direction = "NEUTRAL"

    predicted = str(direction or "").upper()

    if predicted == "NEUTRAL":
        correct = outcome_direction == "NEUTRAL"
    else:
        correct = predicted == outcome_direction

    mfe_pct = None
    mae_pct = None

    if high_price is not None:
        mfe_pct = ((float(high_price) - entry) / entry) * 100.0

    if low_price is not None:
        mae_pct = ((float(low_price) - entry) / entry) * 100.0

    return {
        "future_price": future,
        "return_pct": round(move_pct, 4),
        "outcome_direction": outcome_direction,
        "correct": correct,
        "mfe_pct": round(mfe_pct, 4) if mfe_pct is not None else None,
        "mae_pct": round(mae_pct, 4) if mae_pct is not None else None,
    }

