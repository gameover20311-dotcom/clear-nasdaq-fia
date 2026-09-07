from typing import Any, Dict, Iterable, List


REQUIRED_COLUMNS = [
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
]


def validate_record(row: Dict[str, Any]) -> List[str]:
    errors = []

    for field in REQUIRED_COLUMNS:
        if field not in row:
            errors.append(f"missing:{field}")

    if errors:
        return errors

    if not str(row.get("prediction_id") or "").strip():
        errors.append("empty:prediction_id")

    if not str(row.get("timestamp") or "").strip():
        errors.append("empty:timestamp")

    if not str(row.get("horizon") or "").strip():
        errors.append("empty:horizon")

    return errors


def validate_dataset(
    records: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    rows = list(records)
    invalid = []

    for index, row in enumerate(rows):
        errors = validate_record(row)

        if errors:
            invalid.append({
                "row": index,
                "errors": errors,
            })

    return {
        "total_records": len(rows),
        "valid_records": len(rows) - len(invalid),
        "invalid_records": len(invalid),
        "valid": len(invalid) == 0,
        "errors": invalid,
    }
