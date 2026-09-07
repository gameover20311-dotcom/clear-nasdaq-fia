#!/usr/bin/env python3
"""Rebuild the COGNITIVE calibration model as slope-only (development data only).

WHY
---
The shipped model was a full Platt fit (slope + intercept) on the cognitive raw
probability. Measured on the untouched holdout window, that intercept:

  * flipped the published sign on 26.0% of 4H rows (20/77) and 25.8% of 8H rows
    (16/62) relative to the raw evidence score, and
  * made Brier worse than doing nothing (4H 0.24623 raw -> 0.24957; 8H 0.26930 ->
    0.27001),

because the development window was net bullish and the holdout window was not.

Pinning the intercept at zero keeps genuine sharpening/shrinking and removes the
base-rate injection. sigmoid(a*logit(p)) crosses 50 exactly when p crosses 50, so
calibration can no longer manufacture a direction.

The previous model is archived byte-for-byte before anything is written.

Run:  ./.venv/bin/python build_cognitive_calibration.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from fia.cognitive.calibration import MODEL_PATH, fit_slope_only  # noqa: E402

SOURCE = BACKEND / "fia_backtest_phase30" / "results" / "phase30_cognitive_replay_1y.csv"
DEV_END = "2026-05-01"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    if not SOURCE.exists():
        print("SOURCE_MISSING:", SOURCE)
        return 2

    # Archive the existing model byte-for-byte before replacing it.
    if MODEL_PATH.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive = MODEL_PATH.parent / ("CALIBRATION_ARCHIVE_%s" % stamp)
        archive.mkdir(parents=True, exist_ok=True)
        dest = archive / MODEL_PATH.name
        shutil.copy2(MODEL_PATH, dest)
        print("archived previous model ->", dest)
        print("  previous sha256:", sha256_file(dest))

    rows = list(csv.DictReader(SOURCE.open()))
    models = {
        "available": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "layer": "COGNITIVE",
        "fitted_on": "cognitive raw_probability_before_calibration",
        "method": "Platt slope-only (intercept pinned at 0)",
        "intercept_pinned_at_zero": True,
        "no_base_rate_injection": True,
        "source_dataset": str(SOURCE.relative_to(BACKEND)),
        "source_sha256": sha256_file(SOURCE),
        "source_rows": len(rows),
        "dataset_split": {
            "development": "2025-09-01T00:00:00Z..2026-04-30T23:59:59Z",
            "holdout": "2026-05-01T00:00:00Z..2026-08-31T23:59:59Z",
            "holdout_used_for_fitting": False,
        },
        "horizons": {},
    }

    for horizon in ("4h", "8h"):
        probs, labels, dev_n, elig = [], [], 0, 0
        for row in rows:
            actual = str(row.get("actual_%s" % horizon) or "").upper()
            if actual not in {"BULLISH", "BEARISH"}:
                continue
            raw = row.get("raw_probability_%s" % horizon)
            if raw in (None, ""):
                continue
            elig += 1
            if str(row.get("timestamp") or "") >= DEV_END:
                continue  # holdout is never fitted on
            dev_n += 1
            probs.append(float(raw))
            labels.append(1 if actual == "BULLISH" else 0)

        model = fit_slope_only(probs, labels)
        model["eligible_rows_total"] = elig
        model["development_rows_used"] = dev_n
        models["horizons"][horizon] = model
        print("%s: eligible=%d development_fit_n=%d  a=%s  b=%s" %
              (horizon, elig, dev_n, model.get("a"), model.get("b")))

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(models, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\nWROTE", MODEL_PATH)
    print("sha256", sha256_file(MODEL_PATH))
    return 0


if __name__ == "__main__":
    sys.exit(main())
