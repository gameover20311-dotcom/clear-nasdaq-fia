from typing import Any, Dict


SNAPSHOT_KEYS = (
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
)


def build_snapshot(raw_data: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
    """
    Build a normalized historical FIA snapshot.

    Only data already available at the supplied timestamp should be passed in.
    """
    snapshot = {
        "status": "HISTORICAL",
        "timestamp": timestamp,
        "data": {},
    }

    for key in SNAPSHOT_KEYS:
        snapshot["data"][key] = raw_data.get(key)

    return snapshot


if __name__ == "__main__":
    print("FIA Phase 15 Snapshot Schema: READY")
