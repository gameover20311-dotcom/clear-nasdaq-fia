#!/usr/bin/env python3
"""A6 — SEALED ARTIFACT WRITE GUARD REGRESSION

Proves that running the replay/backtest runners cannot mutate canonical
scientific artifacts.

The hazard was real and measured. Before this guard, a plain regression run
rewrote the phase33 1-year replay summary in place:

    "8h": n 62 -> 61, correct 24 -> 23, accuracy 38.71 -> 37.70,
          brier 0.2719 -> 0.2733, ece 0.1569 -> 0.1681

The two responsible runners were found empirically (hash every tracked
artifact, run each suite entry in isolation, diff, restore):

    fia_backtest_phase33/phase33_full_replay_and_test.py   -> 3 artifacts
    fia_backtest_phase37/phase37_final_backtest.py         -> 5 artifacts

This suite hashes ALL registered artifacts, runs both runners, and proves
byte-for-byte identity afterwards.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from fia.artifact_guard import (  # noqa: E402
    REGEN_ENV_VAR,
    SEALED_PREFIXES,
    guarded_output_path,
    is_protected,
    is_sealed,
    protected_relpaths,
    snapshot_protected,
    verify_protected,
)

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + (("  -> " + str(detail)[:170]) if not ok else ""))


# The runners proven to write into canonical artifact paths.
MUTATING_RUNNERS = [
    "fia_backtest_phase33/phase33_full_replay_and_test.py",
    "fia_backtest_phase37/phase37_final_backtest.py",
]

# ------------------------------------------------------------------ registry
rels = protected_relpaths()
check("A6-1 protected artifact registry is populated", len(rels) >= 100, str(len(rels)))
check("A6-2 registry matches canonical bytes before the run",
      verify_protected()["ok"], str(verify_protected()))

# ------------------------------------------------------------------ guard policy
p33 = BACKEND / "fia_backtest_phase33/results/phase33_full_replay_1y.csv"
seal = BACKEND / "fia_forward_oos/FORWARD_OOS_CAMPAIGN_SEAL.json"

check("A6-3 replay output is recognised as protected", is_protected(p33))
check("A6-4 forward-OOS seal is recognised as SEALED", is_sealed(seal))
check("A6-5 sealed prefixes cover the evidence base",
      all(any(r.startswith(p) for r in rels) for p in SEALED_PREFIXES), str(SEALED_PREFIXES))

os.environ.pop(REGEN_ENV_VAR, None)
check("A6-6 default mode redirects a protected write off the canonical path",
      guarded_output_path(p33) != p33, str(guarded_output_path(p33)))
check("A6-7 an unprotected path passes through untouched",
      guarded_output_path(BACKEND / "nonexistent_scratch.json") == BACKEND / "nonexistent_scratch.json")

os.environ[REGEN_ENV_VAR] = "1"
import importlib  # noqa: E402
import fia.artifact_guard as _g  # noqa: E402
importlib.reload(_g)
check("A6-8 regeneration flag permits a NON-sealed canonical write",
      _g.guarded_output_path(p33) == p33, str(_g.guarded_output_path(p33)))
check("A6-9 regeneration flag STILL refuses a SEALED path",
      _g.guarded_output_path(seal) != seal, str(_g.guarded_output_path(seal)))
os.environ.pop(REGEN_ENV_VAR, None)
importlib.reload(_g)

# ------------------------------------------------------------------ the real proof
before = snapshot_protected()
runner_rc = {}
for rel in MUTATING_RUNNERS:
    script = BACKEND / rel
    if not script.exists():
        runner_rc[rel] = "ABSENT"
        continue
    proc = subprocess.run([sys.executable, str(script)], cwd=str(BACKEND),
                          capture_output=True, text=True, timeout=600)
    runner_rc[rel] = proc.returncode
after = snapshot_protected()

check("A6-10 both artifact-writing runners executed",
      all(v == 0 for v in runner_rc.values()), str(runner_rc))

changed = sorted(r for r in before if before[r] != after[r])
check("A6-11 ALL protected artifacts are byte-for-byte identical after the run",
      changed == [], f"{len(changed)} changed: {changed[:6]}")
check("A6-12 registry still verifies after the run",
      verify_protected()["ok"], str(verify_protected()))

# ------------------------------------------------------------------ determinism
check("A6-13 hashing is deterministic across two consecutive snapshots",
      snapshot_protected() == after)

failed = [n for n, ok, _ in CHECKS if not ok]
print()
print("=" * 46)
if failed:
    print("A6 ARTIFACT GUARD: FAIL")
    print("failed =", failed)
    raise SystemExit(1)
print(f"A6 ARTIFACT GUARD: PASS  ({len(CHECKS)}/{len(CHECKS)})")
print(f"protected_artifacts        = {len(rels)}")
print("sealed_artifacts_writable  = NO (even with regeneration flag)")
print("canonical_bytes_mutated    = NO")
print("artifacts_deleted_or_regenerated = NO")
print("=" * 46)
