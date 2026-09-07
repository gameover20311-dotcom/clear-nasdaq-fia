from collections import defaultdict
from typing import Any, Dict, Iterable


def analyze_regimes(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate historical outcomes by regime and horizon.
    Records should already contain realized outcomes.
    """
    groups = defaultdict(list)

    for record in records:
        regime = str(record.get("regime") or "UNKNOWN")
        horizon = str(record.get("horizon") or "UNKNOWN")
        groups[(regime, horizon)].append(record)

    result = {}

    for (regime, horizon), rows in sorted(groups.items()):
        valid_returns = [
            float(r["return_pct"])
            for r in rows
            if r.get("return_pct") is not None
        ]

        known_correct = [
            bool(r["correct"])
            for r in rows
            if r.get("correct") is not None
        ]

        result[f"{regime}|{horizon}"] = {
            "regime": regime,
            "horizon": horizon,
            "observations": len(rows),
            "accuracy": (
                sum(known_correct) / len(known_correct)
                if known_correct else None
            ),
            "average_return_pct": (
                sum(valid_returns) / len(valid_returns)
                if valid_returns else None
            ),
        }

    return result
