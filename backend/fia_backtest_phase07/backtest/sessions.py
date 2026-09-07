from datetime import datetime, timezone
from typing import Any, Optional


# Default UTC session windows.
# Boundaries are [start, end).
SESSION_WINDOWS = {
    "ASIA": (0, 8),
    "LONDON": (8, 13),
    "NEW_YORK": (13, 21),
    "OFF_SESSION": (21, 24),
}


def _parse_timestamp(timestamp: Any) -> Optional[datetime]:
    if timestamp is None:
        return None

    value = str(timestamp).strip()
    if not value:
        return None

    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (TypeError, ValueError):
        return None


def classify_session(timestamp: Any) -> str:
    """
    Classify a timestamp into a trading session using UTC.

    The function is deliberately independent of live FIA logic.
    """
    dt = _parse_timestamp(timestamp)

    if dt is None:
        return "UNKNOWN"

    hour = dt.hour

    for session, (start, end) in SESSION_WINDOWS.items():
        if start <= hour < end:
            return session

    return "UNKNOWN"


def classify_record(record: dict) -> str:
    return classify_session(record.get("timestamp"))
