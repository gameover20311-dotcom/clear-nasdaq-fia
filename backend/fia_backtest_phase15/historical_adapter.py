from typing import Any, Dict

from .snapshot_schema import build_snapshot


def prediction_to_snapshot(
    row: Dict[str, Any],
) -> Dict[str, Any]:
    timestamp = row.get("timestamp")

    if not timestamp:
        raise ValueError("Historical prediction is missing timestamp")

    raw_data = {}

    for key in (
        "nq_structure",
        "spx_confirmation",
        "dxy",
        "us10y",
        "mega_cap",
        "semis",
        "breadth",
        "news",
        "macro_calendar",
        "earnings",
    ):
        raw_data[key] = row.get(key)

    return build_snapshot(
        raw_data=raw_data,
        timestamp=timestamp,
    )


if __name__ == "__main__":
    print("FIA Phase 15 Historical Adapter: READY")
