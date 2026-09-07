#!/usr/bin/env python3
"""
CLEAR NASDAQ — FIA
MASTER 1-YEAR FULL PROJECT BACKTEST RUNNER

Runs on the user's CURRENT local project so it uses the real .env, cached data,
latest maintenance patches, and exact code currently installed.

It does NOT change production weights and does NOT enable broker execution.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if (HERE / "fia").exists() and (HERE / "main.py").exists():
    BACKEND = HERE
elif (HERE.parent / "backend" / "fia").exists():
    BACKEND = HERE.parent / "backend"
else:
    raise RuntimeError("Could not locate CLEAR NASDAQ FIA backend")
REPORT_DIR = BACKEND / "fia_master_backtest_1y_results"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_PATH = REPORT_DIR / f"master_1y_backtest_{RUN_ID}.log"
JSON_PATH = REPORT_DIR / f"master_1y_backtest_{RUN_ID}.json"

# Curated to test the whole final system without mutating weights.
# Some items are integrity/architecture tests, some are genuine historical replays.
JOBS = [
    ("Phase 22 truth/consistency", "fia_backtest_phase22/phase22_truth_consistency_test.py", "INTEGRITY"),
    ("Phase 23 data reliability", "fia_backtest_phase23/phase23_data_reliability_test.py", "DATA"),
    ("Phase 24 accuracy engine", "fia_backtest_phase24/phase24_accuracy_engine_test.py", "INTEGRITY"),
    ("Phase 25 chart confluence", "fia_backtest_phase25/phase25_chart_confluence_test.py", "INTEGRITY"),
    ("Phase 26 learning validation", "fia_backtest_phase26/phase26_learning_validation_test.py", "INTEGRITY"),
    ("Phase 27 final integration", "fia_backtest_phase27/phase27_final_integration_audit.py", "INTEGRITY"),
    ("Phase 29 truth test", "fia_backtest_phase29/phase29_truth_test.py", "INTEGRITY"),
    ("Phase 30 cognitive replay", "fia_backtest_phase30/phase30_cognitive_replay.py", "REPLAY"),
    ("Phase 30 cognitive integrity", "fia_backtest_phase30/phase30_integrity_test.py", "INTEGRITY"),
    ("Phase 31 vision/confluence", "fia_backtest_phase31/phase31_remaining_two_test.py", "INTEGRITY"),
    ("Phase 32 premove integrity", "fia_backtest_phase32/phase32_premove_max_integrity_test.py", "INTEGRITY"),
    ("Phase 32 premove validation", "fia_backtest_phase32/phase32_premove_max_validation.py", "REPLAY"),
    ("Phase 33 institutional integrity", "fia_backtest_phase33/phase33_integrity_test.py", "INTEGRITY"),
    ("Phase 33 full replay", "fia_backtest_phase33/phase33_full_replay.py", "REPLAY"),
    ("Phase 34 all-points integrity", "fia_backtest_phase34/phase34_integrity_test.py", "INTEGRITY"),
    ("Phase 34 full replay", "fia_backtest_phase34/phase34_full_replay.py", "REPLAY"),
    ("Phase 35 one-year one-shot replay", "fia_backtest_phase35/phase35_one_shot.py", "FULL_1Y_REPLAY"),
    ("Phase 35 integrity", "fia_backtest_phase35/phase35_integrity_test.py", "INTEGRITY"),
    ("Phase 36 ablation lab", "fia_backtest_phase36/phase36_ablation_lab.py", "RESEARCH_REPLAY"),
    ("Phase 36 integrity", "fia_backtest_phase36/phase36_integrity_test.py", "INTEGRITY"),
    ("Phase 37 final lock integrity", "fia_backtest_phase37/phase37_final_integrity_test.py", "INTEGRITY"),
    ("Zero-cost liquidity deterministic test", "fia_backtest_zero_cost_liquidity/test_zero_cost_liquidity.py", "LIQUIDITY"),
]

def emit(msg: str):
    print(msg, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

def run_job(name: str, rel: str, kind: str):
    p = BACKEND / rel
    if not p.exists():
        return {
            "name": name, "path": rel, "kind": kind,
            "status": "MISSING", "returncode": None, "seconds": 0.0,
        }

    emit("\n" + "=" * 88)
    emit(f"RUNNING: {name}")
    emit(f"KIND: {kind}")
    emit(f"FILE: {rel}")
    emit("=" * 88)

    start = time.time()
    proc = subprocess.Popen(
        [sys.executable, "-u", str(p)],
        cwd=str(BACKEND),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=os.environ.copy(),
    )
    output = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        output.append(line)
        emit(line)
    rc = proc.wait()
    seconds = round(time.time() - start, 2)
    status = "PASS" if rc == 0 else "FAIL"
    emit(f"\nRESULT: {name} => {status} ({seconds}s)")
    return {
        "name": name, "path": rel, "kind": kind,
        "status": status, "returncode": rc, "seconds": seconds,
        "tail": output[-25:],
    }

def main():
    emit("CLEAR NASDAQ — FIA · MASTER 1-YEAR FULL PROJECT BACKTEST")
    emit(f"backend={BACKEND}")
    emit(f"run_id={RUN_ID}")
    emit("production weights mutation=NO")
    emit("broker execution=NO")
    emit("goal=historical replay + module integrity + data/leakage/liquidity validation")

    results = []
    for job in JOBS:
        results.append(run_job(*job))

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    summary = {
        "run_id": RUN_ID,
        "backend": str(BACKEND),
        "jobs_total": len(results),
        "counts": counts,
        "all_nonmissing_pass": all(r["status"] in {"PASS", "MISSING"} for r in results),
        "results": results,
        "log_path": str(LOG_PATH),
    }
    JSON_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    emit("\n" + "#" * 88)
    emit("MASTER BACKTEST SUMMARY")
    emit("#" * 88)
    emit(json.dumps(counts, indent=2))
    emit(f"JSON report: {JSON_PATH}")
    emit(f"Full log: {LOG_PATH}")

    fails = [r for r in results if r["status"] == "FAIL"]
    if fails:
        emit("\nFAILED JOBS:")
        for r in fails:
            emit(f"- {r['name']} -> {r['path']}")
        raise SystemExit(1)

    emit("\n✅ MASTER 1-YEAR FULL PROJECT BACKTEST RUN COMPLETE")

if __name__ == "__main__":
    main()
