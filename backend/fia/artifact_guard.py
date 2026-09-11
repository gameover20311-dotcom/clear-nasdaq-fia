# CLEAR NASDAQ — SEALED ARTIFACT WRITE GUARD  (A6)
#
# WHY THIS EXISTS
# ---------------
# Running the regression suite was proven to silently overwrite sealed
# scientific artifacts. Measured example, phase33 1-year replay summary:
#
#     "8h": n 62 -> 61, correct 24 -> 23, accuracy 38.71 -> 37.70,
#           brier 0.2719 -> 0.2733, ece 0.1569 -> 0.1681
#
# Nobody asked for that. It happened because several "tests" are in fact replay
# RUNNERS that rewrite their own canonical output. A test suite that can mutate
# historical scientific evidence is not a test suite; it is an uncontrolled
# write path into the record.
#
# The two runners were identified empirically (hash every tracked artifact,
# run each suite entry in isolation, diff, restore) rather than by reading code:
#
#   fia_backtest_phase33/phase33_full_replay_and_test.py  -> 3 artifacts
#   fia_backtest_phase37/phase37_final_backtest.py        -> 5 artifacts
#
# and the underlying write sites are:
#
#   fia_backtest_phase33/phase33_full_replay.py   OUT / SUM / CAL
#   fia_backtest_phase34/phase34_full_replay.py   OUT
#   fia/phase35_replay_engine.py                  summary + trace
#   fia/phase35_data_foundation.py                backfill_manifest.json
#   fia/phase35_enrichment.py                     enriched_pti.jsonl,
#                                                 enrichment_summary.json
#
# None of those write paths is reachable from a live API route; the phase35 API
# only READS. Guarding them therefore changes no production behaviour.
#
# POLICY
# ------
# Default is READ-ONLY with respect to every artifact listed in
# protected_artifacts.json. A guarded writer is transparently redirected to a
# per-run directory under backend/.artifact_runs/, which is not canonical and
# is not version controlled. Canonical bytes are never touched.
#
# Regeneration is possible but must be intentional: FIA_ARTIFACT_REGEN=1.
# Even then, SEALED paths (the Forward-OOS ledger/seal, the cognitive ledger,
# and the phase29/phase30 replay sources the calibration was fitted on) are
# ALWAYS refused, because those are the evidence base itself.
#
# This module never deletes, regenerates or "repairs" an artifact. A hash
# mismatch against the registry is evidence to be reported, not a prompt to
# re-record the registry.
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path(__file__).resolve().parent / "protected_artifacts.json"
RUN_ROOT = BACKEND / ".artifact_runs"

REGEN_ENV_VAR = "FIA_ARTIFACT_REGEN"

# Paths under these prefixes are the scientific evidence base. They are refused
# even when the regeneration flag is set.
SEALED_PREFIXES = (
    "fia_forward_oos/",
    "fia_cognitive_data/",
    "fia_backtest_phase29/results/",
    "fia_backtest_phase30/results/",
)

_REGISTRY: Optional[Dict[str, str]] = None


def _registry() -> Dict[str, str]:
    global _REGISTRY
    if _REGISTRY is None:
        try:
            _REGISTRY = dict(json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["artifacts"])
        except Exception:
            _REGISTRY = {}
    return _REGISTRY


def protected_relpaths() -> List[str]:
    return sorted(_registry().keys())


def _relpath(path: Any) -> Optional[str]:
    try:
        return str(Path(path).resolve().relative_to(BACKEND)).replace(os.sep, "/")
    except Exception:
        return None


def is_protected(path: Any) -> bool:
    rel = _relpath(path)
    return bool(rel and rel in _registry())


def is_sealed(path: Any) -> bool:
    rel = _relpath(path)
    return bool(rel and any(rel.startswith(p) for p in SEALED_PREFIXES))


def regeneration_enabled() -> bool:
    return str(os.getenv(REGEN_ENV_VAR, "")).strip().lower() in {"1", "true", "yes", "on"}


_RUN_DIR: Optional[Path] = None


def run_dir() -> Path:
    """Per-process non-canonical output directory. Created lazily."""
    global _RUN_DIR
    if _RUN_DIR is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        _RUN_DIR = RUN_ROOT / f"{stamp}-{os.getpid()}"
    return _RUN_DIR


def guarded_output_path(path: Any) -> Path:
    """Return the path a runner may actually write to.

    Unprotected paths pass through untouched. Protected paths are redirected to
    the per-run directory unless regeneration is explicitly enabled, and SEALED
    paths are redirected no matter what.
    """
    target = Path(path)
    rel = _relpath(target)
    if rel is None or rel not in _registry():
        return target
    if is_sealed(target) or not regeneration_enabled():
        redirected = run_dir() / rel
        redirected.parent.mkdir(parents=True, exist_ok=True)
        return redirected
    return target


def sha256_of(path: Any) -> Optional[str]:
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def snapshot_protected() -> Dict[str, Optional[str]]:
    """Current SHA-256 of every registered artifact."""
    return {rel: sha256_of(BACKEND / rel) for rel in protected_relpaths()}


def verify_protected() -> Dict[str, Any]:
    """Compare artifacts on disk against the recorded canonical hashes."""
    reg = _registry()
    now = snapshot_protected()
    mismatched = sorted(r for r in reg if now.get(r) is not None and now[r] != reg[r])
    missing = sorted(r for r in reg if now.get(r) is None)
    return {
        "ok": not mismatched and not missing,
        "registry_schema": "FIA_PROTECTED_ARTIFACTS_V1",
        "count": len(reg),
        "mismatched": mismatched,
        "missing": missing,
        "regeneration_enabled": regeneration_enabled(),
    }
