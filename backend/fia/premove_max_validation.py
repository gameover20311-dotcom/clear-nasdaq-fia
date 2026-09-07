# CLEAR NASDAQ — FIA PRE-MOVE MAX validation utilities (Phase 32)
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .premove_calibration import DEFAULT_OUTCOMES
from .premove_engine import _f


def _read(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            if line.strip():
                out.append(json.loads(line))
        except Exception:
            pass
    return out


def _rows(rows: List[Dict[str, Any]], horizon: str) -> List[Tuple[float, int]]:
    out = []
    key = f"actual_{horizon}"
    # Accept either new max probability field or legacy pre-move probability.
    for r in rows:
        actual = str(r.get(key) or "").upper()
        p = r.get("premove_max_bullish_probability")
        if p in (None, ""):
            p = r.get("premove_bullish_probability")
        if actual not in {"BULLISH", "BEARISH"} or p in (None, ""):
            continue
        out.append((_f(p) / 100.0, 1 if actual == "BULLISH" else 0))
    return out


def _wilson(correct: int, n: int, z: float = 1.96) -> Optional[Tuple[float, float]]:
    if n <= 0:
        return None
    p = correct / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / den
    return max(0.0, center - margin), min(1.0, center + margin)


def _metrics(data: List[Tuple[float, int]]) -> Dict[str, Any]:
    n = len(data)
    if not n:
        return {"n": 0, "status": "NO_RESOLVED_ROWS"}
    eps = 1e-9
    correct = sum((p >= 0.5) == bool(y) for p, y in data)
    brier = sum((p - y) ** 2 for p, y in data) / n
    logloss = -sum(y * math.log(max(eps, min(1 - eps, p))) + (1 - y) * math.log(max(eps, min(1 - eps, 1 - p))) for p, y in data) / n
    bins = []
    ece = 0.0
    for lo, hi in ((0, .4), (.4, .5), (.5, .6), (.6, .7), (.7, 1.000001)):
        sel = [(p, y) for p, y in data if lo <= p < hi]
        if not sel:
            bins.append({"band": f"{int(lo*100)}-{int(min(1,hi)*100)}", "n": 0, "mean_p": None, "observed": None})
            continue
        mp = sum(p for p, _ in sel) / len(sel)
        obs = sum(y for _, y in sel) / len(sel)
        ece += len(sel) / n * abs(mp - obs)
        bins.append({"band": f"{int(lo*100)}-{int(min(1,hi)*100)}", "n": len(sel), "mean_p": round(mp * 100, 1), "observed": round(obs * 100, 1)})
    ci = _wilson(correct, n)
    return {
        "n": n,
        "correct": correct,
        "accuracy": round(100 * correct / n, 2),
        "accuracy_95pct_wilson": [round(100 * ci[0], 2), round(100 * ci[1], 2)] if ci else None,
        "brier": round(brier, 4),
        "log_loss": round(logloss, 4),
        "ece": round(ece, 4),
        "naive_50_brier": 0.25,
        "calibration_bins": bins,
    }


def validation_report_max(outcomes_path: Path | str = DEFAULT_OUTCOMES) -> Dict[str, Any]:
    rows = _read(Path(outcomes_path))
    m4 = _metrics(_rows(rows, "4h"))
    m8 = _metrics(_rows(rows, "8h"))
    min_n = min(m4.get("n", 0), m8.get("n", 0))
    # 200 resolved is still not a guarantee; it merely permits research calibration review.
    status = "OOS_RESEARCH_REVIEW_ALLOWED" if min_n >= 200 else "COLLECTING_FORWARD_EVIDENCE"
    return {
        "ok": True,
        "module": "FIA PRE-MOVE MAX VALIDATION",
        "status": status,
        "4h": m4,
        "8h": m8,
        "minimum_resolved_for_research_review": 200,
        "claim_policy": {
            "90pct_not_assumed": True,
            "holdout_must_remain_untouched": True,
            "thresholds_must_be_frozen_before_holdout": True,
            "market_grade_requires_out_of_sample_evidence": True,
        },
    }
