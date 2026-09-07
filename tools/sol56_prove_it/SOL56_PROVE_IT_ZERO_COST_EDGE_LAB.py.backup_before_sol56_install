#!/usr/bin/env python3
"""
CLEAR NASDAQ — SOL 5.6 "PROVE IT" ZERO-COST EDGE LAB
====================================================

Purpose
-------
One-file, fail-closed research/audit runner for CLEAR NASDAQ — FIA.

What it DOES:
1) Audits the FINAL A-to-Z JSON report math and truth flags.
2) Finds row-level historical prediction CSVs inside the project.
3) Builds a chronological DEVELOPMENT / UNTOUCHED HOLDOUT split.
4) Searches selectivity policies ONLY on development data.
5) Locks the selected policy before touching holdout.
6) Evaluates the untouched holdout exactly once.
7) Compares candidate vs base and writes a reproducible JSON evidence pack.
8) Refuses "WORLD #1", "90%", or market-grade claims when evidence is insufficient.

What it DOES NOT do:
- Fabricate missing L2/L3, gamma, ETF flow, volume delta, macro history, or outcomes.
- Tune on the holdout.
- Hide losing rows.
- Claim a backtest when only aggregate JSON exists.
- Execute broker orders.

Zero-cost: standard-library only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import re
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


VERSION = "SOL56-PROVE-IT-1.0.0"
DEFAULT_REPORT_NAMES = (
    "CLEAR_NASDAQ_FINAL_A_TO_Z_ONE_YEAR_REPORT.json",
    "CLEAR_NASDAQ_FINAL_A_TO_Z_REPORT.json",
)

LEAK_TOKENS = (
    "future", "outcome", "actual", "correct", "target", "label",
    "mfe", "mae", "resolved", "resolution", "result", "pnl",
)

DIRECTION_MAP = {
    "BULLISH": 1, "BULL": 1, "LONG": 1, "UP": 1, "BUY": 1, "1": 1,
    "BEARISH": 0, "BEAR": 0, "SHORT": 0, "DOWN": 0, "SELL": 0, "0": 0,
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip().replace("%", "")
    if not s:
        return None
    try:
        v = float(s)
        if math.isfinite(v):
            return v
    except Exception:
        return None
    return None


def parse_boolish(x: Any) -> Optional[bool]:
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    if s in {"true", "1", "yes", "y", "pass", "correct"}:
        return True
    if s in {"false", "0", "no", "n", "fail", "incorrect"}:
        return False
    return None


def norm_dir(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip().upper()
    if s in {"BULLISH", "BULL", "LONG", "UP", "BUY"}:
        return "BULLISH"
    if s in {"BEARISH", "BEAR", "SHORT", "DOWN", "SELL"}:
        return "BEARISH"
    if s in {"NEUTRAL", "FLAT", "NO_EDGE", "NONE"}:
        return "NEUTRAL"
    return None


def parse_ts(x: Any) -> Optional[datetime]:
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    # unix seconds / milliseconds
    try:
        v = float(s)
        if v > 10_000_000_000:
            v /= 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    except Exception:
        return None


def wilson(correct: int, n: int, z: float = 1.959963984540054) -> Tuple[Optional[float], Optional[float]]:
    if n <= 0:
        return None, None
    p = correct / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / den
    return 100 * (center - margin), 100 * (center + margin)


def brier_score(rows: Sequence[Dict[str, Any]], prob_col: Optional[str], outcome_col: str) -> Optional[float]:
    if not prob_col:
        return None
    vals = []
    for r in rows:
        p = safe_float(r.get(prob_col))
        y = norm_dir(r.get(outcome_col))
        if p is None or y not in {"BULLISH", "BEARISH"}:
            continue
        if p > 1.0:
            p /= 100.0
        p = min(1.0, max(0.0, p))
        yy = 1.0 if y == "BULLISH" else 0.0
        vals.append((p - yy) ** 2)
    return sum(vals) / len(vals) if vals else None


def exact_accuracy(rows: Sequence[Dict[str, Any]], pred_col: str, outcome_col: str) -> Dict[str, Any]:
    n = 0
    c = 0
    for r in rows:
        p = norm_dir(r.get(pred_col))
        y = norm_dir(r.get(outcome_col))
        if p is None or y is None:
            continue
        n += 1
        c += int(p == y)
    lo, hi = wilson(c, n)
    return {
        "n": n,
        "correct": c,
        "incorrect": n - c,
        "accuracy": round(100 * c / n, 4) if n else None,
        "wilson95": [round(lo, 4), round(hi, 4)] if lo is not None else None,
    }


def infer_column(columns: Sequence[str], candidates: Sequence[str], contains: Sequence[str] = ()) -> Optional[str]:
    low = {c.lower(): c for c in columns}
    for c in candidates:
        if c.lower() in low:
            return low[c.lower()]
    for c in columns:
        lc = c.lower()
        if contains and all(tok.lower() in lc for tok in contains):
            return c
    return None


def discover_csvs(root: Path, max_files: int = 5000) -> List[Tuple[int, Path, List[str]]]:
    hits = []
    count = 0
    for p in root.rglob("*.csv"):
        count += 1
        if count > max_files:
            break
        try:
            with p.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                header = next(reader, [])
        except Exception:
            continue
        if not header:
            continue
        low = [h.lower() for h in header]
        score = 0
        name = p.name.lower()
        if "historical_prediction" in name:
            score += 20
        if "prediction" in name:
            score += 12
        if "backtest" in str(p).lower():
            score += 8
        if "timestamp" in low:
            score += 6
        if "direction" in low or "prediction" in low:
            score += 6
        if any("outcome" in c for c in low):
            score += 8
        if "correct" in low:
            score += 6
        if "confidence" in low:
            score += 3
        if "regime" in low:
            score += 3
        if score:
            hits.append((score, p, header))
    hits.sort(key=lambda x: (-x[0], str(x[1])))
    return hits


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def find_report(root: Path, explicit: Optional[str]) -> Optional[Path]:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return p if p.exists() else None
    for name in DEFAULT_REPORT_NAMES:
        p = root / name
        if p.exists():
            return p
    candidates = list(root.rglob("CLEAR_NASDAQ*REPORT*.json"))
    return sorted(candidates)[-1] if candidates else None


def audit_report(report_path: Path) -> Dict[str, Any]:
    with report_path.open("r", encoding="utf-8") as f:
        r = json.load(f)

    checks: List[Dict[str, Any]] = []
    hard_fail = False

    def add(name: str, ok: bool, evidence: Any):
        nonlocal hard_fail
        checks.append({"check": name, "ok": bool(ok), "evidence": evidence})
        if not ok:
            hard_fail = True

    # Core arithmetic
    for h in ("4h", "8h"):
        m = r.get("truth_foundation", {}).get("metrics", {}).get("horizons", {}).get(h, {})
        n, c, reported = m.get("n"), m.get("correct"), m.get("accuracy")
        if isinstance(n, int) and isinstance(c, int) and n > 0 and isinstance(reported, (int, float)):
            calc = 100 * c / n
            add(f"{h}_truth_accuracy_math", abs(calc - reported) <= 0.02,
                {"reported": reported, "recomputed": round(calc, 6), "n": n, "correct": c})
        else:
            add(f"{h}_truth_accuracy_math", False, "missing fields")

    # Truth flags
    tf = r.get("truth_foundation", {})
    add("false_outcomes_counted", tf.get("metrics", {}).get("false_outcomes_are_counted") is True,
        tf.get("metrics", {}).get("false_outcomes_are_counted"))
    add("prediction_digest_preserved", tf.get("prediction_digest_preserved") is True,
        {"before": tf.get("prediction_digest_before"), "after": tf.get("prediction_digest_after")})
    add("legacy_fake_perfect_rejected",
        tf.get("legacy_phase28_claim", {}).get("status") == "REJECTED",
        tf.get("legacy_phase28_claim"))

    reg = r.get("regression_suite", {})
    add("regression_suite_all_pass",
        reg.get("all_pass") is True and reg.get("pass") == reg.get("total"),
        {"pass": reg.get("pass"), "total": reg.get("total"), "all_pass": reg.get("all_pass")})

    safety = r.get("safety", {})
    add("fake_claims_blocked", safety.get("fake_accuracy_claims_blocked") is True, safety)
    add("broker_execution_disabled", safety.get("broker_execution") is False, safety)

    final = r.get("final_decision", {})
    add("world_number_one_not_falsely_claimed",
        final.get("number_one_claim_supported") is False,
        final)

    return {
        "report": str(report_path),
        "sha256": sha256_file(report_path),
        "generated_at": r.get("generated_at"),
        "name": r.get("name"),
        "status": r.get("status"),
        "hard_fail": hard_fail,
        "checks": checks,
        "source_summary": {
            "forecasts": r.get("window", {}).get("forecasts"),
            "baseline_4h": r.get("core_baseline", {}).get("4h"),
            "baseline_8h": r.get("core_baseline", {}).get("8h"),
            "phase37_oos": r.get("phase37_candidate_oos"),
            "licensed_presence": r.get("phase35_full_replay", {}).get("licensed_feed_presence"),
        }
    }


@dataclass(frozen=True)
class Policy:
    min_conf: Optional[float] = None
    regimes: Tuple[str, ...] = ()
    grades: Tuple[str, ...] = ()
    min_agreement: Optional[float] = None

    def label(self) -> str:
        parts = []
        if self.min_conf is not None:
            parts.append(f"conf>={self.min_conf:g}")
        if self.regimes:
            parts.append("regime=" + ",".join(self.regimes))
        if self.grades:
            parts.append("grade=" + ",".join(self.grades))
        if self.min_agreement is not None:
            parts.append(f"agree>={self.min_agreement:g}")
        return " | ".join(parts) if parts else "ALL"

    def accepts(self, row: Dict[str, Any], cols: Dict[str, Optional[str]]) -> bool:
        if self.min_conf is not None:
            c = safe_float(row.get(cols.get("confidence") or ""))
            if c is None:
                return False
            if c <= 1.0:
                c *= 100.0
            if c < self.min_conf:
                return False

        if self.regimes:
            c = cols.get("regime")
            if not c:
                return False
            if str(row.get(c, "")).strip().upper() not in self.regimes:
                return False

        if self.grades:
            c = cols.get("grade")
            if not c:
                return False
            if str(row.get(c, "")).strip().upper() not in self.grades:
                return False

        if self.min_agreement is not None:
            c = safe_float(row.get(cols.get("agreement") or ""))
            if c is None:
                return False
            if c > 1.0:
                c /= 100.0
            if c < self.min_agreement:
                return False

        return True


def infer_schema(rows: Sequence[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    columns = list(rows[0].keys()) if rows else []
    return {
        "timestamp": infer_column(columns,
            ["timestamp", "time", "datetime", "created_at", "forecast_timestamp"]),
        "horizon": infer_column(columns,
            ["horizon", "forecast_horizon", "horizon_hours"]),
        "prediction": infer_column(columns,
            ["direction", "prediction_direction", "predicted_direction", "forecast_direction", "prediction"]),
        "outcome": infer_column(columns,
            ["outcome_direction", "actual_direction", "resolved_direction", "future_direction"]),
        "correct": infer_column(columns, ["correct", "is_correct"]),
        "confidence": infer_column(columns,
            ["confidence", "forecast_confidence", "decision_strength", "probability_confidence"]),
        "bull_prob": infer_column(columns,
            ["bullish_probability", "bull_probability", "prob_bullish", "p_bullish"]),
        "bear_prob": infer_column(columns,
            ["bearish_probability", "bear_probability", "prob_bearish", "p_bearish"]),
        "regime": infer_column(columns, ["regime", "market_regime"]),
        "grade": infer_column(columns, ["setup_grade", "grade", "trade_grade", "quality_grade"]),
        "agreement": infer_column(columns,
            ["agreement", "evidence_agreement", "agreement_score", "confluence_score"]),
    }


def horizon_match(row: Dict[str, Any], horizon_col: Optional[str], hours: int) -> bool:
    if not horizon_col:
        return True
    s = str(row.get(horizon_col, "")).strip().lower()
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if nums:
        try:
            return abs(float(nums[0]) - hours) < 1e-9
        except Exception:
            pass
    return s in {f"{hours}h", f"{hours}hr", f"{hours}hours"}


def prepare_rows(rows: Sequence[Dict[str, Any]], schema: Dict[str, Optional[str]], hours: int) -> List[Dict[str, Any]]:
    pred_col = schema["prediction"]
    out_col = schema["outcome"]
    ts_col = schema["timestamp"]
    if not pred_col or not out_col:
        return []

    usable = []
    for i, r in enumerate(rows):
        if not horizon_match(r, schema["horizon"], hours):
            continue
        if norm_dir(r.get(pred_col)) is None or norm_dir(r.get(out_col)) is None:
            continue
        rr = dict(r)
        rr["__row_index__"] = i
        rr["__ts__"] = parse_ts(r.get(ts_col)) if ts_col else None
        usable.append(rr)

    # Chronological if possible; stable row order otherwise.
    if any(r.get("__ts__") is not None for r in usable):
        floor = datetime(1900, 1, 1, tzinfo=timezone.utc)
        usable.sort(key=lambda x: (x.get("__ts__") or floor, x["__row_index__"]))
    return usable


def score_policy(rows: Sequence[Dict[str, Any]], policy: Policy, schema: Dict[str, Optional[str]]) -> Dict[str, Any]:
    selected = [r for r in rows if policy.accepts(r, schema)]
    metrics = exact_accuracy(selected, schema["prediction"], schema["outcome"])
    metrics["selected_rows"] = len(selected)
    metrics["coverage_pct"] = round(100 * len(selected) / len(rows), 4) if rows else 0.0

    prob_col = schema.get("bull_prob")
    if not prob_col and schema.get("bear_prob"):
        # Brier inversion is handled separately below.
        vals = []
        for r in selected:
            p = safe_float(r.get(schema["bear_prob"]))
            y = norm_dir(r.get(schema["outcome"]))
            if p is None or y not in {"BULLISH", "BEARISH"}:
                continue
            if p > 1:
                p /= 100
            p_bull = 1 - p
            yy = 1.0 if y == "BULLISH" else 0.0
            vals.append((p_bull - yy) ** 2)
        metrics["brier"] = round(sum(vals) / len(vals), 6) if vals else None
        metrics["binary_probability_n"] = len(vals)
    else:
        b = brier_score(selected, prob_col, schema["outcome"])
        metrics["brier"] = round(b, 6) if b is not None else None
        metrics["binary_probability_n"] = None
    return metrics


def build_policies(rows: Sequence[Dict[str, Any]], schema: Dict[str, Optional[str]]) -> List[Policy]:
    policies = [Policy()]

    conf_values = []
    if schema.get("confidence"):
        conf_values = [55, 60, 65, 70, 75, 80]
        policies += [Policy(min_conf=x) for x in conf_values]

    regimes = []
    if schema.get("regime"):
        regimes = sorted({
            str(r.get(schema["regime"], "")).strip().upper()
            for r in rows if str(r.get(schema["regime"], "")).strip()
        })
        regimes = [r for r in regimes if r not in {"NONE", "NAN", ""}]
        for reg in regimes[:12]:
            policies.append(Policy(regimes=(reg,)))
            for c in conf_values:
                policies.append(Policy(min_conf=c, regimes=(reg,)))

    grades = []
    if schema.get("grade"):
        grades = sorted({
            str(r.get(schema["grade"], "")).strip().upper()
            for r in rows if str(r.get(schema["grade"], "")).strip()
        })
        grades = [g for g in grades if g not in {"NONE", "NAN", ""}]
        for g in grades[:12]:
            policies.append(Policy(grades=(g,)))
            for c in conf_values:
                policies.append(Policy(min_conf=c, grades=(g,)))

    agreements = []
    if schema.get("agreement"):
        agreements = [0.6, 0.7, 0.8, 0.9]
        for a in agreements:
            policies.append(Policy(min_agreement=a))
            for c in conf_values:
                policies.append(Policy(min_conf=c, min_agreement=a))

    # Controlled combinations: avoid combinatorial explosion.
    if regimes and grades:
        for reg in regimes[:8]:
            for g in grades[:8]:
                policies.append(Policy(regimes=(reg,), grades=(g,)))
    if regimes and agreements:
        for reg in regimes[:8]:
            for a in agreements:
                policies.append(Policy(regimes=(reg,), min_agreement=a))

    # Deduplicate
    seen = set()
    out = []
    for p in policies:
        k = (p.min_conf, p.regimes, p.grades, p.min_agreement)
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def time_series_cv_select(dev: Sequence[Dict[str, Any]], schema: Dict[str, Optional[str]]) -> Tuple[Policy, Dict[str, Any]]:
    policies = build_policies(dev, schema)
    n = len(dev)
    if n < 40:
        return Policy(), {"status": "INSUFFICIENT_DEV_ROWS", "n": n}

    # Expanding-window validation. Each fold score uses only earlier data to define
    # candidate universe; no holdout is touched.
    cut1 = max(20, int(n * 0.55))
    cut2 = max(cut1 + 10, int(n * 0.75))
    folds = [(dev[:cut1], dev[cut1:cut2]), (dev[:cut2], dev[cut2:])]
    rankings = []

    min_val_n = max(8, int(n * 0.05))
    for p in policies:
        fold_stats = []
        valid = True
        for _, val in folds:
            m = score_policy(val, p, schema)
            if (m["n"] or 0) < min_val_n:
                valid = False
                break
            fold_stats.append(m)
        if not valid or not fold_stats:
            continue

        accs = [m["accuracy"] for m in fold_stats if m["accuracy"] is not None]
        coverages = [m["coverage_pct"] for m in fold_stats]
        lows = [m["wilson95"][0] for m in fold_stats if m["wilson95"]]
        if not accs:
            continue
        # Conservative objective: reward lower confidence bound and repeatability,
        # penalize tiny coverage.
        mean_acc = sum(accs) / len(accs)
        mean_low = sum(lows) / len(lows) if lows else 0.0
        mean_cov = sum(coverages) / len(coverages)
        stability = statistics.pstdev(accs) if len(accs) > 1 else 0.0
        objective = mean_low + 0.10 * mean_acc + 0.02 * min(mean_cov, 50.0) - 0.15 * stability

        rankings.append({
            "policy": p,
            "objective": objective,
            "mean_validation_accuracy": mean_acc,
            "mean_validation_wilson_low": mean_low,
            "mean_validation_coverage_pct": mean_cov,
            "validation_accuracy_stdev": stability,
            "folds": fold_stats,
        })

    if not rankings:
        return Policy(), {"status": "NO_POLICY_MET_MINIMUM_SAMPLE", "n": n}

    rankings.sort(
        key=lambda x: (
            x["objective"],
            x["mean_validation_accuracy"],
            x["mean_validation_coverage_pct"]
        ),
        reverse=True
    )
    best = rankings[0]
    return best["policy"], {
        "status": "LOCKED_ON_DEVELOPMENT_ONLY",
        "selected_policy": best["policy"].label(),
        "selection_metrics": {k: v for k, v in best.items() if k != "policy"},
        "top_10": [
            {
                "policy": x["policy"].label(),
                "objective": round(x["objective"], 6),
                "mean_validation_accuracy": round(x["mean_validation_accuracy"], 4),
                "mean_validation_wilson_low": round(x["mean_validation_wilson_low"], 4),
                "mean_validation_coverage_pct": round(x["mean_validation_coverage_pct"], 4),
            }
            for x in rankings[:10]
        ],
    }


def evaluate_dataset(path: Path, development_fraction: float = 0.70) -> Dict[str, Any]:
    rows = load_csv(path)
    if not rows:
        return {"status": "EMPTY_CSV", "path": str(path)}

    schema = infer_schema(rows)
    if not schema["prediction"] or not schema["outcome"]:
        return {
            "status": "NO_DIRECTIONAL_OUTCOME_SCHEMA",
            "path": str(path),
            "columns": list(rows[0].keys()),
            "inferred_schema": schema,
        }

    horizons = {}
    for hours in (4, 8):
        hr = prepare_rows(rows, schema, hours)
        if len(hr) < 30:
            horizons[f"{hours}h"] = {
                "status": "INSUFFICIENT_ROWS",
                "usable_rows": len(hr),
            }
            continue

        split = max(1, min(len(hr) - 1, int(len(hr) * development_fraction)))
        dev = hr[:split]
        holdout = hr[split:]

        # Base holdout is computed BEFORE candidate filtering, but candidate selection
        # never sees these values.
        base_dev = score_policy(dev, Policy(), schema)

        # LOCK candidate using development only.
        policy, selection = time_series_cv_select(dev, schema)

        # Now, and only now, evaluate holdout once.
        base_holdout = score_policy(holdout, Policy(), schema)
        candidate_holdout = score_policy(holdout, policy, schema)

        base_acc = base_holdout.get("accuracy")
        cand_acc = candidate_holdout.get("accuracy")
        base_brier = base_holdout.get("brier")
        cand_brier = candidate_holdout.get("brier")

        acc_delta = None if base_acc is None or cand_acc is None else cand_acc - base_acc
        brier_delta = None if base_brier is None or cand_brier is None else cand_brier - base_brier

        n_ok = (candidate_holdout.get("n") or 0) >= 40
        improvement_ok = (
            (acc_delta is not None and acc_delta >= 1.0)
            or (brier_delta is not None and brier_delta <= -0.005)
        )
        approval = bool(n_ok and improvement_ok)

        horizons[f"{hours}h"] = {
            "status": "PASS_EVALUATED",
            "rows": len(hr),
            "development_rows": len(dev),
            "untouched_holdout_rows": len(holdout),
            "schema": schema,
            "base_development": base_dev,
            "selection": selection,
            "locked_policy": policy.label(),
            "base_holdout": base_holdout,
            "candidate_holdout": candidate_holdout,
            "accuracy_delta_pp": round(acc_delta, 4) if acc_delta is not None else None,
            "brier_delta": round(brier_delta, 6) if brier_delta is not None else None,
            "approval_rule": "candidate holdout n>=40 AND (accuracy improves >=1pp OR Brier improves >=0.005)",
            "approval_pass": approval,
        }

    approvals = [
        x.get("approval_pass")
        for x in horizons.values()
        if isinstance(x, dict) and x.get("status") == "PASS_EVALUATED"
    ]
    overall = bool(approvals) and all(approvals)
    return {
        "status": "EVALUATED",
        "path": str(path),
        "sha256": sha256_file(path),
        "row_count": len(rows),
        "inferred_schema": schema,
        "horizons": horizons,
        "overall_oos_approval": overall,
        "production_decision": "CANDIDATE_ELIGIBLE_FOR_FORWARD_VALIDATION" if overall else "KEEP_EXISTING_BASELINE",
    }


def choose_prediction_csv(root: Path, explicit: Optional[str]) -> Tuple[Optional[Path], List[Dict[str, Any]]]:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return (p if p.exists() else None), []

    discovered = discover_csvs(root)
    summary = [
        {"score": s, "path": str(p), "columns": h}
        for s, p, h in discovered[:20]
    ]
    if not discovered:
        return None, summary

    # Prefer first CSV that actually contains both prediction and outcome directions.
    for _, p, _ in discovered[:50]:
        try:
            rows = load_csv(p)
        except Exception:
            continue
        if not rows:
            continue
        sc = infer_schema(rows)
        if sc["prediction"] and sc["outcome"]:
            return p, summary
    return None, summary


def main() -> int:
    ap = argparse.ArgumentParser(description="CLEAR NASDAQ SOL5.6 PROVE-IT ZERO-COST EDGE LAB")
    ap.add_argument("--project-root", default=".", help="CLEAR NASDAQ project root")
    ap.add_argument("--report", default=None, help="Path to final A-to-Z report JSON")
    ap.add_argument("--predictions", default=None, help="Path to row-level historical predictions CSV")
    ap.add_argument("--dev-fraction", type=float, default=0.70, help="Chronological development fraction (default 0.70)")
    ap.add_argument("--out", default="SOL56_PROVE_IT_RESULT.json", help="Output JSON filename")
    args = ap.parse_args()

    root = Path(args.project_root).expanduser().resolve()
    if not root.exists():
        print(f"ERROR: project root does not exist: {root}", file=sys.stderr)
        return 2

    result: Dict[str, Any] = {
        "tool": "CLEAR NASDAQ — SOL 5.6 PROVE IT",
        "version": VERSION,
        "generated_at": now_utc(),
        "project_root": str(root),
        "truth_policy": {
            "no_fake_accuracy": True,
            "no_future_leakage_by_design": True,
            "holdout_used_for_selection": False,
            "missing_paid_data_fabricated": False,
            "world_number_one_claim_auto_granted": False,
        },
    }

    report_path = find_report(root, args.report)
    if report_path:
        try:
            result["report_audit"] = audit_report(report_path)
        except Exception as e:
            result["report_audit"] = {"status": "ERROR", "error": repr(e)}
    else:
        result["report_audit"] = {"status": "REPORT_NOT_FOUND"}

    pred_path, discovered = choose_prediction_csv(root, args.predictions)
    result["dataset_discovery_top20"] = discovered

    if pred_path:
        try:
            result["oos_edge_lab"] = evaluate_dataset(pred_path, args.dev_fraction)
        except Exception as e:
            result["oos_edge_lab"] = {"status": "ERROR", "path": str(pred_path), "error": repr(e)}
    else:
        result["oos_edge_lab"] = {
            "status": "BLOCKED_NEEDS_ROW_LEVEL_HISTORY",
            "reason": (
                "Aggregate report JSON can be audited, but a NEW backtest cannot be honestly "
                "performed without timestamped row-level predictions/outcomes. No result is fabricated."
            ),
        }

    audit_ok = (
        isinstance(result.get("report_audit"), dict)
        and result["report_audit"].get("hard_fail") is False
    )
    oos = result.get("oos_edge_lab", {})
    oos_approved = isinstance(oos, dict) and oos.get("overall_oos_approval") is True

    result["final_gate"] = {
        "report_truth_audit_pass": audit_ok,
        "new_candidate_oos_approval": oos_approved,
        "world_number_one_claim_supported": False,
        "market_grade_claim_supported": bool(audit_ok and oos_approved),
        "decision": (
            "FORWARD_VALIDATE_LOCKED_CANDIDATE"
            if audit_ok and oos_approved
            else "DO_NOT_PROMOTE_NEW_CANDIDATE"
        ),
        "note": (
            "A global #1 claim requires independent external benchmarks and sustained forward/OOS superiority. "
            "This runner intentionally cannot self-award that title."
        ),
    }

    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 72)
    print("CLEAR NASDAQ — SOL 5.6 PROVE IT")
    print("=" * 72)
    print("Result:", out)
    print("Report audit:", result.get("report_audit", {}).get("hard_fail") is False)
    print("OOS edge lab:", result.get("oos_edge_lab", {}).get("status"))
    print("Decision:", result["final_gate"]["decision"])
    print("WORLD #1 auto-claim: BLOCKED (requires independent proof)")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
