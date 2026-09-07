from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fia_backtest_phase15.backtest.resolver import resolve_record
from fia_backtest_phase16.backtest.engine import (
    load_records,
    resolved_records,
    summarize,
)
from fia_backtest_phase17.backtest.evaluator import evaluate


def run_pipeline(
    dataset_path: str,
    report_path: str,
) -> Dict[str, Any]:
    dataset = Path(dataset_path)

    if not dataset.exists():
        report = {
            "status": "NO_REAL_DATA",
            "dataset_exists": False,
            "records_total": 0,
            "records_resolved": 0,
            "walk_forward": None,
            "robustness": {
                "enough_data_for_robustness": False,
                "performance_claim_allowed": False,
            },
            "performance_claim": (
                "Not available: no real historical "
                "prediction/outcome dataset."
            ),
        }
    else:
        records = load_records(str(dataset))
        resolved = resolved_records(records)
        summary = summarize(records)
        evaluation = evaluate(records)

        report = {
            "status": "EVALUATED" if resolved else "NO_RESOLVED_DATA",
            "dataset_exists": True,
            "records_total": len(records),
            "records_resolved": len(resolved),
            "summary": summary,
            "walk_forward": evaluation.get("walk_forward"),
            "robustness": evaluation.get("robustness"),
            "performance_claim": (
                "Performance calculated from real records."
                if resolved
                else
                "Not available: no resolved real outcomes."
            ),
        }

    destination = Path(report_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    return report
