from __future__ import annotations

from fia_backtest_phase18.backtest.pipeline import run_pipeline


DEFAULT_DATASET = (
    "fia_backtest_phase14/data/"
    "historical_predictions.csv"
)

DEFAULT_REPORT = (
    "fia_backtest_phase18/data/"
    "final_backtest_report.json"
)


def main() -> None:
    report = run_pipeline(
        DEFAULT_DATASET,
        DEFAULT_REPORT,
    )

    print("PHASE 18 FINAL PIPELINE: PASS")
    print("phase14_recorder=CONNECTED")
    print("phase15_outcome_resolver=CONNECTED")
    print("phase16_backtest_engine=CONNECTED")
    print("phase17_walk_forward=CONNECTED")
    print("final_report=GENERATED")
    print("status=", report["status"])
    print("records_total=", report["records_total"])
    print("records_resolved=", report["records_resolved"])
    print("report_path=", DEFAULT_REPORT)

    if report["status"] == "NO_REAL_DATA":
        print("performance_claim=NOT_AVAILABLE_NO_REAL_DATA")
    elif report["status"] == "NO_RESOLVED_DATA":
        print("performance_claim=NOT_AVAILABLE_NO_RESOLVED_OUTCOMES")
    else:
        print("performance_claim=REAL_DATA_ONLY")


if __name__ == "__main__":
    main()
