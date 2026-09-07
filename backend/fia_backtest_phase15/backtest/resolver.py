from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional


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


def outcome_direction(entry_price: float, future_price: float) -> str:
    if future_price > entry_price:
        return "BULLISH"
    if future_price < entry_price:
        return "BEARISH"
    return "NEUTRAL"


def signed_return_pct(entry_price: float, future_price: float) -> float:
    if entry_price == 0:
        raise ValueError("entry_price cannot be zero")
    return ((future_price - entry_price) / entry_price) * 100.0


def resolve_record(
    record: Dict[str, Any],
    future_price: float,
) -> Dict[str, Any]:
    entry_price = float(record["entry_price"])

    if entry_price <= 0:
        raise ValueError("entry_price must be positive")

    future_price = float(future_price)
    direction = str(record.get("direction", "")).upper()

    outcome = outcome_direction(entry_price, future_price)
    ret = signed_return_pct(entry_price, future_price)

    if direction == "BULLISH":
        correct = outcome == "BULLISH"
    elif direction == "BEARISH":
        correct = outcome == "BEARISH"
    elif direction == "NEUTRAL":
        correct = outcome == "NEUTRAL"
    else:
        correct = None

    resolved = dict(record)
    resolved["future_price"] = future_price
    resolved["return_pct"] = round(ret, 6)
    resolved["outcome_direction"] = outcome
    resolved["correct"] = correct

    return resolved


def resolve_csv(
    input_path: str,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    source = Path(input_path)

    if not source.exists():
        return {
            "source_exists": False,
            "records_read": 0,
            "records_resolved": 0,
            "output_path": output_path,
        }

    with source.open("r", newline="", encoding="utf-8") as f:
        rows: List[Dict[str, Any]] = list(csv.DictReader(f))

    resolved_rows = 0
    output_rows: List[Dict[str, Any]] = []

    for row in rows:
        if not row.get("entry_price") or not row.get("future_price"):
            output_rows.append(row)
            continue

        try:
            resolved = resolve_record(
                row,
                float(row["future_price"]),
            )
            output_rows.append(resolved)
            resolved_rows += 1
        except (TypeError, ValueError):
            output_rows.append(row)

    destination = Path(output_path) if output_path else source

    with destination.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=FIELDS,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(output_rows)

    return {
        "source_exists": True,
        "records_read": len(rows),
        "records_resolved": resolved_rows,
        "output_path": str(destination),
    }
