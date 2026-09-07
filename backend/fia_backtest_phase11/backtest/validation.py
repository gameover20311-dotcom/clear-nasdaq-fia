from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (TypeError, ValueError):
        return None


def _accuracy(rows: List[Dict[str, Any]]):
    values = [
        bool(row["correct"])
        for row in rows
        if row.get("correct") is not None
    ]

    return sum(values) / len(values) if values else None


def _average_return(rows: List[Dict[str, Any]]):
    values = []

    for row in rows:
        try:
            if row.get("return_pct") is not None:
                values.append(float(row["return_pct"]))
        except (TypeError, ValueError):
            continue

    return sum(values) / len(values) if values else None


def chronological_holdout_split(
    records: Iterable[Dict[str, Any]],
    holdout_size: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Split records chronologically.

    The final holdout_size observations are completely separated from
    the development set.
    """
    if holdout_size <= 0:
        raise ValueError("holdout_size must be positive")

    rows = []

    for record in records:
        timestamp = _parse_timestamp(record.get("timestamp"))

        if timestamp is not None:
            rows.append((timestamp, record))

    rows.sort(key=lambda item: item[0])

    if holdout_size >= len(rows):
        raise ValueError(
            "holdout_size must be smaller than the number of valid records"
        )

    development = [
        record for _, record in rows[:-holdout_size]
    ]

    holdout = [
        record for _, record in rows[-holdout_size:]
    ]

    return development, holdout


def evaluate_holdout(
    records: Iterable[Dict[str, Any]],
    holdout_size: int,
) -> Dict[str, Any]:
    development, holdout = chronological_holdout_split(
        records,
        holdout_size,
    )

    timestamps = [
        _parse_timestamp(row.get("timestamp"))
        for row in holdout
    ]

    timestamps = [x for x in timestamps if x is not None]

    return {
        "development_observations": len(development),
        "holdout_observations": len(holdout),
        "holdout_start": (
            timestamps[0].isoformat()
            if timestamps else None
        ),
        "holdout_end": (
            timestamps[-1].isoformat()
            if timestamps else None
        ),
        "holdout_accuracy": _accuracy(holdout),
        "holdout_average_return_pct": _average_return(holdout),
    }
