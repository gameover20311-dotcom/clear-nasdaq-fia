from __future__ import annotations

from typing import Any, Dict, List, Optional


def accuracy(records: List[Dict[str, Any]]) -> Optional[float]:
    if not records:
        return None

    resolved = [
        r for r in records
        if str(r.get("correct", "")).strip().lower()
        in {"true", "false", "1", "0", "yes", "no"}
    ]

    if not resolved:
        return None

    correct = sum(
        1
        for r in resolved
        if str(r.get("correct", "")).strip().lower()
        in {"true", "1", "yes"}
    )

    return correct / len(resolved)


def split_walk_forward(
    records: List[Dict[str, Any]],
    development_size: int,
    holdout_size: int,
) -> Dict[str, Any]:
    development = records[:development_size]
    holdout = records[
        development_size:development_size + holdout_size
    ]

    return {
        "development": development,
        "holdout": holdout,
    }


def evaluate_holdout(
    holdout: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "holdout_records": len(holdout),
        "holdout_accuracy": accuracy(holdout),
    }


def robustness_checks(
    records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    resolved = [
        r for r in records
        if r.get("future_price") not in (None, "")
        and r.get("outcome_direction") not in (None, "")
        and r.get("correct") not in (None, "")
    ]

    return {
        "resolved_records": len(resolved),
        "enough_data_for_robustness": len(resolved) >= 20,
        "performance_claim_allowed": len(resolved) > 0,
    }


def evaluate(
    records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not records:
        return {
            "status": "NO_REAL_DATA",
            "records": 0,
            "walk_forward": None,
            "robustness": robustness_checks(records),
        }

    split = split_walk_forward(
        records,
        development_size=max(1, len(records) // 2),
        holdout_size=max(1, len(records) - len(records) // 2),
    )

    holdout_result = evaluate_holdout(split["holdout"])

    return {
        "status": "EVALUATED",
        "records": len(records),
        "development_records": len(split["development"]),
        "holdout_records": len(split["holdout"]),
        "holdout_accuracy": holdout_result["holdout_accuracy"],
        "walk_forward": {
            "development_records": len(split["development"]),
            "holdout_records": len(split["holdout"]),
            "holdout_accuracy": holdout_result["holdout_accuracy"],
        },
        "robustness": robustness_checks(records),
    }
