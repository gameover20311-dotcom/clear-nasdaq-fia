from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


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


def build_walk_forward_windows(
    records: Iterable[Dict[str, Any]],
    train_size: int,
    validation_size: int,
    step_size: Optional[int] = None,
):
    """
    Create chronological rolling walk-forward windows.

    No future observations are allowed into an earlier training window.
    """
    rows = []

    for record in records:
        timestamp = _parse_timestamp(record.get("timestamp"))
        if timestamp is not None:
            rows.append((timestamp, record))

    rows.sort(key=lambda item: item[0])

    if step_size is None:
        step_size = validation_size

    if train_size <= 0 or validation_size <= 0 or step_size <= 0:
        raise ValueError("Window sizes must be positive.")

    windows = []
    start = 0
    window_id = 1

    while start + train_size + validation_size <= len(rows):
        train = [item[1] for item in rows[start:start + train_size]]

        validation_start = start + train_size
        validation = [
            item[1]
            for item in rows[
                validation_start:validation_start + validation_size
            ]
        ]

        train_times = rows[start:start + train_size]
        validation_times = rows[
            validation_start:validation_start + validation_size
        ]

        windows.append({
            "window_id": window_id,
            "train_start": train_times[0][0].isoformat(),
            "train_end": train_times[-1][0].isoformat(),
            "validation_start": validation_times[0][0].isoformat(),
            "validation_end": validation_times[-1][0].isoformat(),
            "train_observations": len(train),
            "validation_observations": len(validation),
            "validation_accuracy": _accuracy(validation),
            "validation_return_pct": _average_return(validation),
        })

        start += step_size
        window_id += 1

    return windows


def summarize_walk_forward(windows):
    accuracies = [
        float(w["validation_accuracy"])
        for w in windows
        if w.get("validation_accuracy") is not None
    ]

    returns = [
        float(w["validation_return_pct"])
        for w in windows
        if w.get("validation_return_pct") is not None
    ]

    return {
        "windows": len(windows),
        "average_validation_accuracy": (
            sum(accuracies) / len(accuracies)
            if accuracies else None
        ),
        "average_validation_return_pct": (
            sum(returns) / len(returns)
            if returns else None
        ),
    }
