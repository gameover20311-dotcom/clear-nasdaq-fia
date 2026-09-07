#!/usr/bin/env python3
"""Revalidate frozen Phase 28 predictions against independent Massive NQ bars.

This does not rerun or retune the forecasting model. It preserves every stored
prediction and replaces the legacy Yahoo outcome lookup with completed 5-minute
bars from the contract selected at the original checkpoint.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fia_backtest_phase28.phase28_data import FuturesCache, NQ_CACHE, parse_dt
from fia_backtest_phase28.truth_metrics import integrity_flags

SOURCE_CSV = ROOT / "fia_backtest_phase28" / "results" / "phase28_market_grade_replay_1y.csv"
OUTDIR = Path(__file__).resolve().parent / "results"
CSV_OUT = OUTDIR / "phase29_outcome_revalidated_1y.csv"
SUMMARY_OUT = OUTDIR / "phase29_outcome_revalidated_1y_summary.json"

NEUTRAL_THRESHOLD_PCT = 0.05
MAX_STALENESS_MINUTES = 15


def direction_from_move(move_pct: Optional[float]) -> Optional[str]:
    if move_pct is None:
        return None
    if move_pct > NEUTRAL_THRESHOLD_PCT:
        return "BULLISH"
    if move_pct < -NEUTRAL_THRESHOLD_PCT:
        return "BEARISH"
    return "NEUTRAL"


def prediction_digest(rows: List[Dict[str, Any]]) -> str:
    frozen = [
        [
            row.get("timestamp"),
            row.get("predicted"),
            row.get("bullish_probability"),
            row.get("bearish_probability"),
        ]
        for row in rows
    ]
    payload = json.dumps(frozen, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def iso_bar_end(row: Optional[Dict[str, Any]]) -> Optional[str]:
    if not row:
        return None
    return (row["timestamp"] + timedelta(minutes=5)).isoformat()


def run() -> Dict[str, Any]:
    with SOURCE_CSV.open(newline="", encoding="utf-8") as handle:
        source_rows = list(csv.DictReader(handle))
    if not source_rows:
        raise SystemExit("Phase 28 source CSV has no frozen predictions")

    nq = FuturesCache(NQ_CACHE)
    if not nq.available:
        raise SystemExit("Massive NQ cache is missing")

    source_digest = prediction_digest(source_rows)
    rows: List[Dict[str, Any]] = []
    unresolved = []

    extra_fields = [
        "outcome_provider", "outcome_contract", "entry_bar_end",
        "outcome_4h_bar_end", "outcome_4h_staleness_min",
        "outcome_8h_bar_end", "outcome_8h_staleness_min",
    ]

    for source in source_rows:
        row = dict(source)
        target = parse_dt(source.get("timestamp"))
        if target is None:
            unresolved.append({"timestamp": source.get("timestamp"), "reason": "invalid timestamp"})
            rows.append(row)
            continue

        contract, entry_row, entry_stale = nq.last_completed(target, MAX_STALENESS_MINUTES)
        out4, stale4 = nq.last_completed_for_contract(
            contract, target + timedelta(hours=4), MAX_STALENESS_MINUTES
        )
        out8, stale8 = nq.last_completed_for_contract(
            contract, target + timedelta(hours=8), MAX_STALENESS_MINUTES
        )
        entry = float(entry_row["close"]) if entry_row else None
        price4 = float(out4["close"]) if out4 else None
        price8 = float(out8["close"]) if out8 else None
        move4 = ((price4 - entry) / entry * 100.0) if entry and price4 is not None else None
        move8 = ((price8 - entry) / entry * 100.0) if entry and price8 is not None else None
        actual4 = direction_from_move(move4)
        actual8 = direction_from_move(move8)
        predicted = str(source.get("predicted") or "").upper()

        row.update({
            "outcome_provider": nq.provider,
            "outcome_contract": contract,
            "entry_bar_end": iso_bar_end(entry_row),
            "entry_nq": entry,
            "entry_staleness_min": entry_stale,
            "nq_4h": price4,
            "outcome_4h_bar_end": iso_bar_end(out4),
            "outcome_4h_staleness_min": stale4,
            "nq_8h": price8,
            "outcome_8h_bar_end": iso_bar_end(out8),
            "outcome_8h_staleness_min": stale8,
            "actual_4h": actual4,
            "actual_8h": actual8,
            "correct_4h": predicted == actual4 if actual4 else None,
            "correct_8h": predicted == actual8 if actual8 else None,
            "move_4h_pct": move4,
            "move_8h_pct": move8,
        })
        if entry is None or price4 is None or price8 is None:
            unresolved.append({"timestamp": target.isoformat(), "contract": contract})
        rows.append(row)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    fields = list(source_rows[0].keys())
    for field in extra_fields:
        if field not in fields:
            insert_at = fields.index("entry_nq") if "entry_nq" in fields else len(fields)
            fields.insert(insert_at, field)
    with CSV_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    metrics = integrity_flags(rows)
    same_source = sum(1 for row in rows if row.get("outcome_provider") == nq.provider)
    preserved_digest = prediction_digest(rows)
    core_pass = (
        source_digest == preserved_digest
        and same_source == len(rows)
        and metrics["scheduled_resolution"]["4h"]["resolution_rate"] >= 0.95
        and metrics["scheduled_resolution"]["8h"]["resolution_rate"] >= 0.95
        and not metrics["perfect_result_warning"]
    )
    summary = {
        "phase": "PHASE 29 - AUTHENTICITY FOUNDATION",
        "status": "OUTCOME_REVALIDATED_CORE_ONLY" if core_pass else "FAIL",
        "official_market_grade_claim_eligible": False,
        "reason_official_claim_is_withheld": (
            "Predictions and outcomes are revalidated, but the full forecast must be rerun "
            "after independent chart-feature detection before any market-grade claim."
        ),
        "frozen_predictions": len(rows),
        "prediction_digest_before": source_digest,
        "prediction_digest_after": preserved_digest,
        "prediction_digest_preserved": source_digest == preserved_digest,
        "outcome_source": nq.provider,
        "outcome_contract_policy": "Entry-time dominant contract frozen for entry, 4H and 8H outcomes",
        "completed_bar_policy": "Only completed 5-minute bars at or before the requested timestamp; max staleness 15 minutes. Older bars remain unresolved, never converted to flat/neutral.",
        "metrics": metrics,
        "unresolved_examples": unresolved[:20],
        "legacy_phase28_claim": {
            "status": "REJECTED",
            "reported_4h_accuracy": 100.0,
            "reported_8h_accuracy": 100.0,
            "root_cause": "False outcomes were converted to an empty value and excluded from the denominator.",
        },
        "research_only": True,
        "broker_execution": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
