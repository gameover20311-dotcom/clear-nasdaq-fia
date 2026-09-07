from typing import Any, Dict, Optional


def calculate_outcome(
    record: Dict[str, Any],
    future_price: float,
) -> Dict[str, Any]:

    entry_price = record.get("entry_price")

    if entry_price in (None, ""):
        raise ValueError("entry_price is required")

    entry = float(entry_price)
    future = float(future_price)

    if entry == 0:
        raise ValueError("entry_price cannot be zero")

    return_pct = ((future - entry) / entry) * 100.0

    if return_pct > 0:
        outcome_direction = "BULLISH"
    elif return_pct < 0:
        outcome_direction = "BEARISH"
    else:
        outcome_direction = "NEUTRAL"

    direction = str(
        record.get("direction") or ""
    ).upper()

    correct: Optional[bool]

    if direction in {"BULLISH", "BEARISH"}:
        correct = direction == outcome_direction
    else:
        correct = None

    result = dict(record)

    result.update({
        "future_price": future,
        "return_pct": round(return_pct, 6),
        "outcome_direction": outcome_direction,
        "correct": correct,
    })

    return result
