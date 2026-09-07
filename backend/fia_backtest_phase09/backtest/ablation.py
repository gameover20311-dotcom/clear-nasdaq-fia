from collections import defaultdict
from typing import Any, Dict, Iterable, List


def _accuracy(rows: List[Dict[str, Any]]):
    values = [
        bool(row["correct"])
        for row in rows
        if row.get("correct") is not None
    ]
    return sum(values) / len(values) if values else None


def _average_return(rows: List[Dict[str, Any]]):
    values = []

    for row in rows:
        try:
            if row.get("return_pct") is not None:
                values.append(float(row["return_pct"]))
        except (TypeError, ValueError):
            continue

    return sum(values) / len(values) if values else None


def ablation_test(
    records: Iterable[Dict[str, Any]],
    signal_to_remove: str,
) -> Dict[str, Any]:
    """
    Descriptive leave-one-signal-out analysis.

    A record is considered 'ablated' when the named signal is absent.
    This does not rerun the FIA model and therefore does not claim causal
    importance.
    """
    rows = list(records)

    baseline_accuracy = _accuracy(rows)
    baseline_return = _average_return(rows)

    ablated = [
        row for row in rows
        if str(row.get("signal") or "") != signal_to_remove
    ]

    ablated_accuracy = _accuracy(ablated)
    ablated_return = _average_return(ablated)

    return {
        "signal_removed": signal_to_remove,
        "baseline_observations": len(rows),
        "ablated_observations": len(ablated),
        "baseline_accuracy": baseline_accuracy,
        "ablated_accuracy": ablated_accuracy,
        "accuracy_delta": (
            ablated_accuracy - baseline_accuracy
            if baseline_accuracy is not None
            and ablated_accuracy is not None
            else None
        ),
        "baseline_return_pct": baseline_return,
        "ablated_return_pct": ablated_return,
        "return_delta_pct": (
            ablated_return - baseline_return
            if baseline_return is not None
            and ablated_return is not None
            else None
        ),
    }


def run_ablation_suite(
    records: Iterable[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    rows = list(records)

    signals = sorted({
        str(row.get("signal"))
        for row in rows
        if row.get("signal")
    })

    result = {}

    for signal in signals:
        result[signal] = ablation_test(rows, signal)

    return result
