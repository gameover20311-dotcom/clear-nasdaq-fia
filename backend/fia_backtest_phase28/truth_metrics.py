"""Strict, dependency-free metrics for FIA point-in-time replays.

The parser deliberately distinguishes ``False`` from missing data.  Using
``value or ""`` here is forbidden because it silently removes every losing
forecast and can turn an ordinary result into a fake 100% result.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def resolved_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower() if value is not None else ""
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def brier(rows: List[Dict[str, Any]], horizon: int) -> Dict[str, Any]:
    values = []
    for row in rows:
        actual = str(row.get("actual_{}h".format(horizon)) or "").upper()
        if actual not in {"BULLISH", "BEARISH"}:
            continue
        try:
            probability = float(row.get("bullish_probability")) / 100.0
        except (TypeError, ValueError):
            continue
        observed = 1.0 if actual == "BULLISH" else 0.0
        values.append((probability - observed) ** 2)
    return {
        "n": len(values),
        "brier": round(sum(values) / len(values), 4) if values else None,
    }


def metric(rows: List[Dict[str, Any]], horizon: int) -> Dict[str, Any]:
    resolved = []
    key = "correct_{}h".format(horizon)
    for row in rows:
        outcome = resolved_bool(row.get(key))
        if outcome is not None:
            resolved.append((row, outcome))

    if not resolved:
        return {
            "n": 0,
            "correct": 0,
            "incorrect": 0,
            "resolution_rate": 0.0,
            "accuracy": None,
            "brier": None,
        }

    correct = sum(1 for _, outcome in resolved if outcome)
    total = len(resolved)
    return {
        "n": total,
        "correct": correct,
        "incorrect": total - correct,
        "resolution_rate": round(total / len(rows), 4) if rows else 0.0,
        "accuracy": round(100.0 * correct / total, 2),
        "brier": brier([row for row, _ in resolved], horizon)["brier"],
    }


def _parse_timestamp(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def futures_outcome_scheduled(checkpoint: Any, horizon: int) -> bool:
    """Whether a regular CME equity-futures bar is expected at the horizon.

    This narrow schedule guard prevents Friday +8H checkpoints (Saturday UTC)
    from being mislabeled as provider failures. Exchange holidays can still
    produce explicit unresolved rows and remain visible in the report.
    """
    timestamp = _parse_timestamp(checkpoint)
    if timestamp is None:
        return False
    target = timestamp + timedelta(hours=horizon)
    weekday = target.weekday()
    if weekday == 5:
        return False
    if weekday == 6 and target.hour < 22:
        return False
    if weekday == 4 and target.hour > 22:
        return False
    return True


def scheduled_resolution(rows: List[Dict[str, Any]], horizon: int) -> Dict[str, Any]:
    eligible = [
        row for row in rows
        if futures_outcome_scheduled(row.get("timestamp"), horizon)
    ]
    resolved = sum(
        1 for row in eligible
        if resolved_bool(row.get("correct_{}h".format(horizon))) is not None
    )
    return {
        "eligible_n": len(eligible),
        "resolved_n": resolved,
        "resolution_rate": round(resolved / len(eligible), 4) if eligible else 0.0,
    }


def integrity_flags(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    horizons = {"4h": metric(rows, 4), "8h": metric(rows, 8)}
    schedule = {
        "4h": scheduled_resolution(rows, 4),
        "8h": scheduled_resolution(rows, 8),
    }
    perfect_result_warning = any(
        block["n"] >= 50
        and block["accuracy"] is not None
        and block["accuracy"] >= 99.5
        for block in horizons.values()
    )
    return {
        "forecasts": len(rows),
        "horizons": horizons,
        "scheduled_resolution": schedule,
        "perfect_result_warning": perfect_result_warning,
        "false_outcomes_are_counted": True,
    }
