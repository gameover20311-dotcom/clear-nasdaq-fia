from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List


REQUIRED_FIELDS = {
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
    "outcome_direction",
    "correct",
}


def load_records(path: str) -> List[Dict[str, Any]]:
    source = Path(path)

    if not source.exists():
        return []

    with source.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate_record(record: Dict[str, Any]) -> bool:
    return REQUIRED_FIELDS.issubset(record.keys())


def resolved_records(
    records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    result = []

    for record in records:
        if not validate_record(record):
            continue

        if record.get("future_price") in (None, ""):
            continue

        if record.get("outcome_direction") in (None, ""):
            continue

        if record.get("correct") in (None, ""):
            continue

        result.append(record)

    return result


def accuracy(records: List[Dict[str, Any]]) -> float | None:
    if not records:
        return None

    correct = 0

    for record in records:
        value = str(record.get("correct", "")).strip().lower()
        if value in {"true", "1", "yes"}:
            correct += 1

    return correct / len(records)


def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    valid = resolved_records(records)

    acc = accuracy(valid)

    return {
        "records_total": len(records),
        "records_resolved": len(valid),
        "records_unresolved": len(records) - len(valid),
        "accuracy": acc,
    }


def run_backtest(path: str) -> Dict[str, Any]:
    records = load_records(path)

    if not records:
        return {
            "dataset_exists": Path(path).exists(),
            "records_total": 0,
            "records_resolved": 0,
            "records_unresolved": 0,
            "accuracy": None,
            "status": "NO_REAL_DATA",
        }

    result = summarize(records)
    result["dataset_exists"] = True
    result["status"] = (
        "READY_FOR_EVALUATION"
        if result["records_resolved"] > 0
        else "NO_RESOLVED_DATA"
    )

    return result
