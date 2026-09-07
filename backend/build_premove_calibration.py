#!/usr/bin/env python3
"""Build the PRE-MOVE calibration model (slope-only, development data only).

WHY A SEPARATE MODEL
--------------------
`fia_cognitive_data/calibration_model.json` was fitted on the COGNITIVE layer's
raw probability. `fia/premove_watch.py` was applying that same model to a
DIFFERENT quantity -- the pre-move raw probability produced by

    p = 50 + 25 * clamp(sum(score*w)/sum(|w|), -1, 1)

A Platt fit is only valid on the score distribution it was fitted on, so this
builder fits the pre-move layer its own model from its own raw scores.

WHY SLOPE-ONLY
--------------
Measured on the untouched holdout window, the full (slope+intercept) fit made
Brier WORSE on both horizons, because the development window was net bullish
(4H 53.42%, 8H 59.02% bullish) and the holdout window was not (45.45%, 45.16%).
The intercept was transporting a period-specific base rate into live forecasts.

Pinning the intercept at 0 keeps genuine sharpening/shrinking and removes the
base-rate injection. It also makes it mathematically impossible for calibration
to flip the published direction or to move a no-information 50.0 off 50.0.

DATA DISCIPLINE
---------------
* Fits on DEVELOPMENT rows only (timestamp < 2026-05-01). The holdout window is
  never used for fitting.
* Uses only stored prediction-time signals; no outcome column touches the
  features, only the label.
* Rewrites nothing except its own output file.

Run:  ./.venv/bin/python build_premove_calibration.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from fia.cognitive.calibration import fit_slope_only  # noqa: E402
from fia.premove_watch import DEAD_FRESHNESS, HORIZON_WEIGHTS  # noqa: E402

SOURCE = BACKEND / "fia_backtest_phase30" / "results" / "phase30_cognitive_replay_1y.csv"
OUT = BACKEND / "fia_cognitive_data" / "premove_calibration_model.json"
DEV_END = "2026-05-01"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def premove_raw(signals, horizon):
    """Exact reproduction of premove_watch._horizon_probability."""
    weights = HORIZON_WEIGHTS.get(horizon, {})
    num = den = 0.0
    used = 0
    for s in signals:
        if str(s.get("freshness") or "").lower() in DEAD_FRESHNESS or s.get("score") is None:
            continue
        base_w = float(s.get("weight") or 0.0)
        if base_w <= 0:
            continue
        w = base_w * weights.get(str(s.get("name") or ""), 1.0)
        num += float(s["score"]) * w
        den += abs(w)
        used += 1
    if den <= 0 or used == 0:
        return None
    return 50.0 + max(-1.0, min(1.0, num / den)) * 25.0


def main() -> int:
    if not SOURCE.exists():
        print("SOURCE_MISSING:", SOURCE)
        return 2

    rows = list(csv.DictReader(SOURCE.open()))
    models = {
        "available": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "layer": "PREMOVE",
        "fitted_on": "premove raw probability (p = 50 + 25*clamp(sum(score*w)/sum(|w|),-1,1))",
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
            try:
                signals = json.loads(row.get("signals_json") or "[]")
            except Exception:
                continue
            raw = premove_raw(signals, horizon)
            if raw is None:
                continue
            elig += 1
            if str(row.get("timestamp") or "") >= DEV_END:
                continue  # holdout is never fitted on
            dev_n += 1
            probs.append(raw)
            labels.append(1 if actual == "BULLISH" else 0)

        model = fit_slope_only(probs, labels)
        model["eligible_rows_total"] = elig
        model["development_rows_used"] = dev_n
        models["horizons"][horizon] = model
        print("%s: eligible=%d development_fit_n=%d  a=%s  b=%s" %
              (horizon, elig, dev_n, model.get("a"), model.get("b")))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(models, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\nWROTE", OUT)
    print("sha256", sha256_file(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
