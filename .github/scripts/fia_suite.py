# CLEAR NASDAQ — regression suite runner and failure classifier (CI harness only)
#
# WHY THIS FILE EXISTS
# --------------------
# The previous inline runner classified any failure whose output contained the
# substring "ModuleNotFoundError" or "ImportError" as NOT_TESTED_ENV. That rule
# is unsound. It cannot tell a genuinely absent third-party dependency from a
# project-local import that is simply broken, and it granted an environment
# exemption to seven checks in a CI environment that had installed every
# declared dependency successfully. A broken project-local import is a FAIL.
#
# It also invoked each entry as `python <subdir>/<entry>.py`, which puts the
# ENTRY'S OWN DIRECTORY on sys.path[0] rather than the backend root. Every entry
# living in a subpackage therefore failed at `from fia... import ...` before a
# single assertion ran. That is a defect in the runner, not in the environment
# and not in the checks.
#
# This file is deliberately OUTSIDE backend/. fia/identity.py fingerprints files
# under the backend root against an explicit per-file registry and treats an
# unclassified file in scope as a hard error, so a harness script placed in
# backend/ would both break the run and change the MODEL/PROTOCOL/INFRASTRUCTURE
# digests. A CI harness must never be able to move a scientific identity.
#
# CLASSIFICATION IS EVIDENCE-BASED
# --------------------------------
# Every non-PASS entry is classified from the LAST exception in its traceback,
# and the exception type, message, final frame and output tail are recorded so
# the classification can be audited rather than trusted:
#
#   PASS                    return code 0 AND evidence the entry actually ran.
#   TRUE_EXTERNAL_ENV_BLOCK a module that is neither project-local nor importable
#                           by this interpreter. In CI this must never occur:
#                           the dependency step installs and verifies the
#                           declared set before the suite runs.
#   PROJECT_IMPORT_DEFECT   an import of a module that EXISTS in this repository
#                           and still failed to resolve. Counts as a failure.
#   MISSING_FIXTURE_OR_DATA imports resolved, then the entry could not find a
#                           data file it requires. Counts as a failure.
#   TIMEOUT                 exceeded the per-entry wall clock.
#   FAIL                    any other non-zero exit, an empty successful process,
#                           or an explicit zero-test result.
#
# There is no category that silently excuses a check. Only
# TRUE_EXTERNAL_ENV_BLOCK is environmental, and CI treats even that as fatal.
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"

ENTRY_GLOBS = (
    "fia/test_*.py",
    "fia_backtest_*/*test*.py",
    "fia_final_cockpit/test_*.py",
    "fia_forward_oos/test_*.py",
    "phase21_live_engine_smoke_test.py",
    "test_reseal_refuses_any_observation_v672.py",
    "clear_nasdaq_brain/tests/run_all.py",
)

# v681 is an immutable PRE-REPAIR equivalence baseline.  It is supposed to hard
# stop after the intentional 2026-09-13 earnings temporal-admission change and
# therefore is forensic evidence, not a current-code PASS gate.  It is not
# deleted or re-recorded.  Current change control is mandatory through v683
# (semantic point-in-time regression) and v684 (proves that swapping ONLY the
# earnings admission method back to its legacy implementation restores v681's
# original digest).
HISTORICAL_ONLY_ENTRIES = {
    "fia/test_providers_snapshot_equivalence_v681.py",
}
REQUIRED_ACTIVE_REPLACEMENTS = {
    "fia/test_earnings_temporal_admission_v683.py",
    "fia/test_providers_snapshot_change_control_v684.py",
}

PER_ENTRY_TIMEOUT = 900

FAILING_STATUSES = (
    "FAIL",
    "PROJECT_IMPORT_DEFECT",
    "MISSING_FIXTURE_OR_DATA",
    "TIMEOUT",
    "TRUE_EXTERNAL_ENV_BLOCK",
)

_EXC_LINE = re.compile(r"^(?P<type>[A-Za-z_][A-Za-z0-9_.]*Error|SystemExit|KeyboardInterrupt)"
                       r"(?::\s*(?P<msg>.*))?$")
_NO_MODULE = re.compile(r"No module named ['\"]([^'\"]+)['\"]")
_CANNOT_IMPORT = re.compile(r"cannot import name ['\"][^'\"]+['\"] from ['\"]([^'\"]+)['\"]")
_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<fn>.*)$')
_ZERO_TEST_PATTERNS = (
    re.compile(r"\bRan\s+0\s+tests?\b", re.IGNORECASE),
    re.compile(r"\bcollected\s+0\s+items?\b", re.IGNORECASE),
    re.compile(r"\b0\s+tests?\s+(?:run|executed|passed)\b", re.IGNORECASE),
)


def discover():
    """Entry paths relative to the backend root.

    Historical-only checks remain in the repository as immutable forensic
    evidence.  They may leave the active set only when an explicit replacement
    gate is present, otherwise discovery fails closed.
    """
    seen = set()
    for pattern in ENTRY_GLOBS:
        seen.update(glob.glob(pattern, root_dir=str(BACKEND)))
    active = seen - HISTORICAL_ONLY_ENTRIES
    missing_replacements = sorted(REQUIRED_ACTIVE_REPLACEMENTS - active)
    if missing_replacements:
        raise RuntimeError(
            "REQUIRED_CHANGE_CONTROL_REPLACEMENT_MISSING:" + ",".join(missing_replacements)
        )
    return sorted(active)


def last_exception(text):
    """Return (type, message, final frame) for the LAST traceback in text."""
    exc_type = exc_msg = frame = None
    for raw in text.splitlines():
        line = raw.rstrip()
        framed = _FRAME.match(line)
        if framed:
            frame = f"{framed.group('file')}:{framed.group('line')} in {framed.group('fn')}"
            continue
        matched = _EXC_LINE.match(line)
        if matched:
            exc_type = matched.group("type").split(".")[-1]
            exc_msg = (matched.group("msg") or "").strip()
    return exc_type, exc_msg, frame


def is_project_local(module):
    """True when the named module actually exists in this repository."""
    top = module.split(".")[0]
    if not top:
        return False
    return (BACKEND / top).is_dir() or (BACKEND / f"{top}.py").is_file()


def is_importable(module):
    """True when this interpreter can resolve the module at all."""
    top = module.split(".")[0]
    probe = (
        "import importlib.util, sys\n"
        f"sys.exit(0 if importlib.util.find_spec({top!r}) else 1)\n"
    )
    try:
        done = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, timeout=60, cwd=str(BACKEND),
        )
    except Exception:
        return False
    return done.returncode == 0


def classify(returncode, output, timed_out):
    """Map one entry's result to a status plus the evidence behind it.

    Exit code 0 is necessary but not sufficient.  A process that exits cleanly
    after running zero tests (or produces no evidence at all) is not allowed to
    manufacture a PASS.
    """
    if timed_out:
        return "TIMEOUT", {"reason": f"exceeded {PER_ENTRY_TIMEOUT}s"}
    if returncode == 0:
        text = str(output or "")
        if not text.strip():
            return "FAIL", {
                "reason": "zero exit with empty output; execution evidence is absent",
                "zero_test_guard": True,
            }
        for pattern in _ZERO_TEST_PATTERNS:
            if pattern.search(text):
                return "FAIL", {
                    "reason": "entry explicitly reported zero tests/items",
                    "zero_test_guard": True,
                }
        return "PASS", {"executed": True}

    exc_type, exc_msg, frame = last_exception(output)
    evidence = {
        "exception_type": exc_type,
        "exception_message": exc_msg,
        "final_frame": frame,
        "returncode": returncode,
    }

    module = None
    if exc_msg:
        found = _NO_MODULE.search(exc_msg) or _CANNOT_IMPORT.search(exc_msg)
        if found:
            module = found.group(1)

    if exc_type in ("ModuleNotFoundError", "ImportError"):
        if module:
            evidence["module"] = module
            evidence["project_local"] = is_project_local(module)
            if evidence["project_local"]:
                evidence["reason"] = (
                    f"{module!r} exists in this repository; the import failed anyway"
                )
                return "PROJECT_IMPORT_DEFECT", evidence
            evidence["importable"] = is_importable(module)
            if not evidence["importable"]:
                evidence["reason"] = (
                    f"{module!r} is not in this repository and this interpreter "
                    f"cannot resolve it"
                )
                return "TRUE_EXTERNAL_ENV_BLOCK", evidence
            evidence["reason"] = (
                f"{module!r} IS importable by this interpreter; the failure is "
                f"in how the entry imports it"
            )
            return "PROJECT_IMPORT_DEFECT", evidence
        evidence["reason"] = "import error naming no external module"
        return "PROJECT_IMPORT_DEFECT", evidence

    if exc_type in ("FileNotFoundError", "IsADirectoryError", "NotADirectoryError"):
        evidence["reason"] = "imports resolved; a required input was absent"
        return "MISSING_FIXTURE_OR_DATA", evidence

    if exc_type is None:
        printed = [line.strip() for line in output.strip().splitlines() if line.strip()]
        evidence["printed_failure"] = printed[-5:]
        evidence["reason"] = (
            "non-zero exit with no traceback; the check reported its own failure"
        )
        return "FAIL", evidence

    evidence["reason"] = "non-zero exit after imports resolved"
    return "FAIL", evidence


def git_dirty(repo_root):
    """Porcelain entries, status code kept."""
    done = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=str(repo_root),
    )
    return sorted(line.strip() for line in done.stdout.splitlines() if line.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--repo-root", default=str(BACKEND.parent))
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(BACKEND)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )

    entries = discover()
    baseline_dirty = git_dirty(repo_root)

    results = {}
    seen_dirty = set(baseline_dirty)
    for entry in entries:
        timed_out = False
        try:
            done = subprocess.run(
                [sys.executable, entry],
                capture_output=True, text=True,
                timeout=PER_ENTRY_TIMEOUT, cwd=str(BACKEND), env=env,
            )
            returncode = done.returncode
            output = (done.stdout or "") + (done.stderr or "")
        except subprocess.TimeoutExpired as expired:
            timed_out = True
            returncode = None
            output = (expired.stdout or "") + (expired.stderr or "") \
                if isinstance(expired.stdout, str) else ""

        status, evidence = classify(returncode, output, timed_out)
        now_dirty = set(git_dirty(repo_root))
        introduced = sorted(now_dirty - seen_dirty)
        seen_dirty |= now_dirty

        record = {"status": status, "evidence": evidence}
        if introduced:
            record["mutated_tracked_files"] = introduced
        tail = output.strip().splitlines()[-25:]
        if status != "PASS":
            record["output_tail"] = tail
        results[entry] = record
        print(f"{status:<24} {entry}", flush=True)

    counts = {}
    for record in results.values():
        counts[record["status"]] = counts.get(record["status"], 0) + 1

    payload = {
        "schema": "FIA_SUITE_RESULT_V3",
        "entry_count": len(entries),
        "counts": counts,
        "historical_only_entries": sorted(HISTORICAL_ONLY_ENTRIES),
        "required_active_replacements": sorted(REQUIRED_ACTIVE_REPLACEMENTS),
        "baseline_dirty": baseline_dirty,
        "mutated_by_suite": sorted(seen_dirty - set(baseline_dirty)),
        "results": results,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print("\nCOUNTS " + json.dumps(counts, sort_keys=True))
    for entry, record in sorted(results.items()):
        if record["status"] == "PASS":
            continue
        evidence = record["evidence"]
        print(f"\n--- {record['status']}  {entry}")
        if evidence.get("exception_type"):
            print(f"    exception : {evidence.get('exception_type')}: "
                  f"{evidence.get('exception_message')}")
            print(f"    frame     : {evidence.get('final_frame')}")
        for line in evidence.get("printed_failure", []):
            print(f"    reported  : {line}")
        print(f"    reason    : {evidence.get('reason')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())