from typing import Any, Dict

from .snapshot_schema import build_snapshot


def replay_forecast(
    build_forecast,
    raw_data: Dict[str, Any],
    timestamp: str,
):
    snapshot = build_snapshot(
        raw_data=raw_data,
        timestamp=timestamp,
    )

    return build_forecast(snapshot)


if __name__ == "__main__":
    print("FIA Phase 15 Replay Engine: READY")
