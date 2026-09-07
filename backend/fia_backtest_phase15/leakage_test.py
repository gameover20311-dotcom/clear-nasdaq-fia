try:
    from .point_in_time import filter_point_in_time
except ImportError:
    from fia_backtest_phase15.point_in_time import filter_point_in_time


def run_leakage_test():
    target = "2026-08-31T17:00:00+00:00"

    records = [
        {"timestamp": "2026-08-31T16:00:00+00:00", "id": "past"},
        {"timestamp": "2026-08-31T17:00:00+00:00", "id": "exact"},
        {"timestamp": "2026-08-31T18:00:00+00:00", "id": "future"},
    ]

    result = filter_point_in_time(records, target)
    ids = [row["id"] for row in result]

    assert "past" in ids
    assert "exact" in ids
    assert "future" not in ids

    print("FIA Phase 15 Leakage Test: PASSED")


if __name__ == "__main__":
    run_leakage_test()
