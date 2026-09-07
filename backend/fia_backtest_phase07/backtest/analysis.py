from collections import defaultdict
from typing import Any, Dict, Iterable


def analyze_sessions(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate historical FIA outcomes by session and horizon.

    Expected record fields:
      timestamp
      horizon
      direction
      probability
      return_pct
      correct

    The function does not manufacture missing outcomes.
    """
    groups = defaultdict(list)

    for record in records:
        session = str(record.get("session") or "UNKNOWN")
        horizon = str(record.get("horizon") or "UNKNOWN")
        groups[(session, horizon)].append(record)

    result = {}

    for (session, horizon), rows in sorted(groups.items()):
        returns = [
            float(row["return_pct"])
            for row in rows
            if row.get("return_pct") is not None
        ]

        correctness = [
            bool(row["correct"])
            for row in rows
            if row.get("correct") is not None
        ]

        probabilities = [
            float(row["probability"])
            for row in rows
            if row.get("probability") is not None
        ]

        result[f"{session}|{horizon}"] = {
            "session": session,
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
            "average_probability": (
                sum(probabilities) / len(probabilities)
                if probabilities else None
            ),
        }

    return result
