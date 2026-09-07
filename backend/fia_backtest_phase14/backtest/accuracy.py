from pathlib import Path
import csv
from collections import Counter


def load_predictions(csv_path):
    path = Path(csv_path)

    if not path.exists():
        return []

    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value):
    if value is None:
        return None
    return str(value).strip().lower() == "true"


def calculate_accuracy(csv_path):
    rows = load_predictions(csv_path)

    resolved = [
        r for r in rows
        if _bool(r.get("correct")) is not None
        and r.get("outcome_direction")
    ]

    total = len(rows)
    resolved_count = len(resolved)

    correct_count = sum(
        1 for r in resolved if _bool(r.get("correct")) is True
    )

    accuracy = (
        (correct_count / resolved_count) * 100.0
        if resolved_count
        else None
    )

    by_direction = {}

    for direction in ("BULLISH", "BEARISH", "NEUTRAL"):
        subset = [
            r for r in resolved
            if str(r.get("direction", "")).upper() == direction
        ]

        correct = sum(
            1 for r in subset if _bool(r.get("correct")) is True
        )

        by_direction[direction] = {
            "total": len(subset),
            "correct": correct,
            "accuracy_pct": (
                round((correct / len(subset)) * 100.0, 2)
                if subset else None
            ),
        }

    confidence_values = []
    correct_confidence = []
    incorrect_confidence = []

    for r in resolved:
        confidence = _float(r.get("confidence"))

        if confidence is None:
            continue

        confidence_values.append(confidence)

        if _bool(r.get("correct")):
            correct_confidence.append(confidence)
        else:
            incorrect_confidence.append(confidence)

    return {
        "total_predictions": total,
        "resolved_predictions": resolved_count,
        "unresolved_predictions": total - resolved_count,
        "correct_predictions": correct_count,
        "incorrect_predictions": resolved_count - correct_count,
        "accuracy_pct": round(accuracy, 2) if accuracy is not None else None,
        "by_direction": by_direction,
        "confidence": {
            "average": (
                round(sum(confidence_values) / len(confidence_values), 2)
                if confidence_values else None
            ),
            "average_when_correct": (
                round(sum(correct_confidence) / len(correct_confidence), 2)
                if correct_confidence else None
            ),
            "average_when_incorrect": (
                round(sum(incorrect_confidence) / len(incorrect_confidence), 2)
                if incorrect_confidence else None
            ),
        },
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    csv_path = root / "fia_backtest_phase14" / "data" / "historical_predictions.csv"

    result = calculate_accuracy(csv_path)

    print("=== FIA BACKTEST ACCURACY ===")
    for key, value in result.items():
        print(f"{key}: {value}")
