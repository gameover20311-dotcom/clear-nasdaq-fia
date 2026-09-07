import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .recorder import resolve_prediction_outcome


def _parse_timestamp(value: str) -> datetime:
    value = value.strip()

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    dt = datetime.fromisoformat(value)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _hours_elapsed(timestamp: str) -> float:
    created = _parse_timestamp(timestamp)
    now = datetime.now(timezone.utc)
    return (now - created).total_seconds() / 3600.0


def find_due_predictions(
    path: str,
) -> list[Dict[str, Any]]:
    """
    Return predictions whose forecast horizon has completed
    and which have not yet been resolved.
    """

    csv_path = Path(path)

    if not csv_path.exists():
        return []

    with csv_path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as f:
        rows = list(csv.DictReader(f))

    due = []

    for row in rows:
        if row.get("future_price"):
            continue

        timestamp = row.get("timestamp")
        horizon = row.get("horizon")

        if not timestamp or not horizon:
            continue

        try:
            horizon_hours = float(horizon)
        except (TypeError, ValueError):
            continue

        if _hours_elapsed(timestamp) >= horizon_hours:
            due.append(row)

    return due


def update_prediction_outcome(
    row: Dict[str, Any],
    future_price: float,
    high_price: Optional[float] = None,
    low_price: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Resolve one completed prediction and return its updated row.
    """

    entry_price = float(row["entry_price"])

    outcome = resolve_prediction_outcome(
        entry_price=entry_price,
        future_price=float(future_price),
        direction=row.get("direction", ""),
        high_price=high_price,
        low_price=low_price,
    )

    updated = dict(row)
    updated.update(outcome)

    return updated


def rewrite_predictions(
    path: str,
    updated_rows: list[Dict[str, Any]],
) -> Path:
    """
    Safely rewrite the prediction CSV with resolved outcomes.
    """

    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    if not updated_rows:
        return csv_path

    fieldnames = list(updated_rows[0].keys())

    temp_path = csv_path.with_suffix(".csv.tmp")

    with temp_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(updated_rows)

    temp_path.replace(csv_path)

    return csv_path

async def get_nq_future_price(
    target_time,
    current_price=None,
):
    """
    Resolve NQ futures price near the requested UTC time.

    Uses yfinance NQ=F 5-minute historical candles so this
    resolver does not depend on Polygon futures permissions.
    """
    import asyncio
    import yfinance as yf

    target = target_time

    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)

    target = target.astimezone(timezone.utc)

    def load_data():
        ticker = yf.Ticker("NQ=F")
        return ticker.history(
            period="5d",
            interval="5m",
            auto_adjust=False,
        )

    try:
        data = await asyncio.to_thread(load_data)
    except Exception as exc:
        print(f"NQ=F historical data error: {exc}")
        return None

    if data is None or data.empty:
        print("NQ=F yfinance returned no historical candles.")
        return None

    try:
        if data.index.tz is None:
            data.index = data.index.tz_localize(timezone.utc)
        else:
            data.index = data.index.tz_convert(timezone.utc)
    except Exception as exc:
        print(f"NQ=F timezone conversion failed: {exc}")
        return None

    best = None
    best_distance = None

    for candle_time, row in data.iterrows():
        try:
            close = row.get("Close")

            if close is None:
                continue

            distance = abs(
                (candle_time.to_pydatetime() - target).total_seconds()
            )

            if best_distance is None or distance < best_distance:
                best_distance = distance
                best = float(close)

        except (TypeError, ValueError, OverflowError):
            continue

    return best

async def resolve_due_predictions(
    path: str,
) -> int:
    """
    Resolve predictions whose forecast horizon has completed.

    Predictions are updated only when an actual historical NQ price
    can be obtained. Unresolved rows remain untouched.
    """
    csv_path = Path(path)

    if not csv_path.exists():
        return 0

    with csv_path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return 0

    changed = 0

    for row in rows:
        if row.get("future_price"):
            continue

        timestamp = row.get("timestamp")
        horizon = row.get("horizon")
        entry_price = row.get("entry_price")

        if not timestamp or not horizon or not entry_price:
            continue

        try:
            horizon_hours = float(horizon)
            entry_price = float(entry_price)
        except (TypeError, ValueError):
            continue

        created = _parse_timestamp(timestamp)
        target_time = created + timedelta(
            hours=horizon_hours
        )

        if datetime.now(timezone.utc) < target_time:
            continue

        future_price = await get_nq_future_price(
            target_time,
            current_price=entry_price,
        )

        if future_price is None:
            continue

        outcome = resolve_prediction_outcome(
            entry_price=entry_price,
            future_price=future_price,
            direction=row.get("direction", ""),
        )

        row.update(outcome)
        changed += 1

    if changed:
        rewrite_predictions(path, rows)

    return changed

