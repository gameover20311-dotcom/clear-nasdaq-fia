import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CACHE_PATH = Path(
    "fia_backtest_phase19/data/earnings_events_sec_verified.json"
)

MEGA_WEIGHTS = {
    "MSFT": 0.10,
    "AAPL": 0.09,
    "AMZN": 0.08,
    "META": 0.07,
    "ALPHABET": 0.10,
    "TSLA": 0.04,
    "NFLX": 0.03,
}

SEMIS = {
    "NVDA", "AMD", "INTC", "QCOM", "SMCI", "AVGO", "MU"
}


def clamp(value, low=-1.0, high=1.0):
    return max(low, min(high, float(value)))


def parse_ts(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_verified_events():
    if not CACHE_PATH.exists():
        raise FileNotFoundError(
            f"Missing verified earnings cache: {CACHE_PATH}"
        )

    payload = json.loads(
        CACHE_PATH.read_text(encoding="utf-8")
    )

    events = payload.get("events") or []
    cleaned = []

    for event in events:
        reveal = parse_ts(event.get("reveal_at"))
        item = dict(event)
        item["_reveal_at"] = reveal
        cleaned.append(item)

    cleaned.sort(key=lambda e: e["_reveal_at"])
    return cleaned


def _direction_sign(direction):
    d = str(direction or "").upper()
    if d == "BULLISH":
        return 1.0
    if d == "BEARISH":
        return -1.0
    return 0.0


def earnings_point_in_time(
    target_timestamp,
    horizon_hours=8,
    released_lookback_hours=24,
):
    """
    Point-in-time earnings logic.

    BEFORE reveal_at:
      - EPS actual/estimate is NOT used.
      - Event is exposed only as upcoming catalyst risk.
      - earnings score stays None (missing directional evidence).

    AFTER reveal_at:
      - Verified Finnhub EPS surprise may become directional.
      - Recent released events are aggregated with the same simple
        positive-vs-negative counting style as the existing FIA
        earnings logic.
    """
    target = parse_ts(target_timestamp)
    events = load_verified_events()

    horizon_end = target + timedelta(hours=horizon_hours)
    released_start = target - timedelta(
        hours=released_lookback_hours
    )

    upcoming = []
    released_recent = []

    for event in events:
        reveal = event["_reveal_at"]

        if target < reveal <= horizon_end:
            upcoming.append(event)

        if released_start <= reveal <= target:
            released_recent.append(event)

    directional_signs = [
        _direction_sign(event.get("surprise_direction"))
        for event in released_recent
        if _direction_sign(
            event.get("surprise_direction")
        ) != 0.0
    ]

    earnings_score = None
    if directional_signs:
        earnings_score = clamp(
            sum(directional_signs)
            / len(directional_signs)
        )

    upcoming_symbols = [
        event.get("symbol")
        for event in upcoming
    ]

    released_symbols = [
        event.get("symbol")
        for event in released_recent
    ]

    combined_mega_weight = sum(
        MEGA_WEIGHTS.get(
            str(event.get("symbol")),
            0.0,
        )
        for event in upcoming
    )

    semi_upcoming_count = sum(
        str(event.get("symbol")) in SEMIS
        for event in upcoming
    )

    hours_to_next = None
    next_event = None

    if upcoming:
        next_event = min(
            upcoming,
            key=lambda e: e["_reveal_at"],
        )
        hours_to_next = (
            next_event["_reveal_at"] - target
        ).total_seconds() / 3600.0

    return {
        "earnings": earnings_score,

        "historical_earnings_evidence": (
            "released_verified"
            if earnings_score is not None
            else (
                "upcoming_verified_catalyst"
                if upcoming
                else "missing"
            )
        ),

        "earnings_released_events": len(
            released_recent
        ),
        "earnings_released_symbols": released_symbols,

        "earnings_upcoming_events": len(upcoming),
        "earnings_upcoming_symbols": upcoming_symbols,

        "earnings_upcoming_within_4h": sum(
            event["_reveal_at"]
            <= target + timedelta(hours=4)
            for event in upcoming
        ),

        "earnings_upcoming_within_8h": len(
            upcoming
        ),

        "earnings_upcoming_mega_weight": round(
            combined_mega_weight,
            4,
        ),

        "earnings_upcoming_semi_count": (
            semi_upcoming_count
        ),

        "earnings_hours_to_next": (
            None
            if hours_to_next is None
            else round(hours_to_next, 3)
        ),

        "earnings_next_symbol": (
            None
            if next_event is None
            else next_event.get("symbol")
        ),

        "earnings_catalyst_risk": bool(upcoming),

        # Important audit flags.
        "earnings_future_eps_used": False,
        "earnings_direction_only_after_reveal": True,
    }


def main():
    target = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "2026-07-29T17:00:00+00:00"
    )

    result = earnings_point_in_time(target)

    print("=== PHASE 19 POINT-IN-TIME EARNINGS ===")
    print("timestamp =", parse_ts(target).isoformat())

    for key, value in result.items():
        print(key, "=", value)

    print("=== POINT-IN-TIME EARNINGS COMPLETE ===")


if __name__ == "__main__":
    main()
