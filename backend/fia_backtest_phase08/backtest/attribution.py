from collections import defaultdict
from typing import Any, Dict, Iterable


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _direction_match(signal_direction, outcome_direction):
    if not signal_direction or not outcome_direction:
        return None

    a = str(signal_direction).strip().upper()
    b = str(outcome_direction).strip().upper()

    bullish = {"BULL", "BULLISH", "LONG", "UP"}
    bearish = {"BEAR", "BEARISH", "SHORT", "DOWN"}

    if a in bullish and b in bullish:
        return True
    if a in bearish and b in bearish:
        return True
    if a in bullish | bearish and b in bullish | bearish:
        return False

    return None


def attribute_signals(
    records: Iterable[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate historical performance for each FIA signal.

    This is descriptive attribution only. It does not infer causality
    and does not modify live FIA weights.
    """
    groups = defaultdict(list)

    for record in records:
        name = str(record.get("signal") or "UNKNOWN")
        horizon = str(record.get("horizon") or "UNKNOWN")
        groups[(name, horizon)].append(record)

    result = {}

    for (signal, horizon), rows in sorted(groups.items()):
        correctness = [
            bool(row["correct"])
            for row in rows
            if row.get("correct") is not None
        ]

        returns = [
            _safe_float(row.get("return_pct"))
            for row in rows
        ]
        returns = [x for x in returns if x is not None]

        scores = [
            _safe_float(row.get("signal_score"))
            for row in rows
        ]
        scores = [x for x in scores if x is not None]

        result[f"{signal}|{horizon}"] = {
            "signal": signal,
            "horizon": horizon,
            "observations": len(rows),
            "accuracy": (
                sum(correctness) / len(correctness)
                if correctness else None
            ),
            "average_return_pct": (
                sum(returns) / len(returns)
                if returns else None
            ),
            "average_signal_score": (
                sum(scores) / len(scores)
                if scores else None
            ),
        }

    return result


def compare_signal_direction(
    records: Iterable[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Optional directional diagnostic.

    Compares each signal's stated direction with the realized direction
    when both are available.
    """
    groups = defaultdict(list)

    for record in records:
        signal = str(record.get("signal") or "UNKNOWN")
        horizon = str(record.get("horizon") or "UNKNOWN")
        groups[(signal, horizon)].append(record)

    result = {}

    for (signal, horizon), rows in sorted(groups.items()):
        matches = []

        for row in rows:
            match = _direction_match(
                row.get("direction"),
                row.get("outcome_direction"),
            )
            if match is not None:
                matches.append(match)

        result[f"{signal}|{horizon}"] = {
            "signal": signal,
            "horizon": horizon,
            "direction_observations": len(matches),
            "direction_alignment": (
                sum(matches) / len(matches)
                if matches else None
            ),
        }

    return result
