# CLEAR NASDAQ — regression suite runner and failure classifier (CI harness only)
#
# The harness distinguishes code/test failures from one explicitly registered
# historical external dataset that is intentionally absent from GitHub. Absence
# is NEVER PASS: an exact registered check may become MISSING_EXTERNAL_DATA /
# NOT_TESTED only when the canonical file is absent and the check fails in the
# exact predeclared way. Wrong bytes, an unknown missing file, or a check that
# passes despite its declared required data being absent are hard failures.
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
EXTERNAL_DATA_REGISTRY = REPO_ROOT / ".github" / "fia_external_data_registry.json"

ENTRY_GLOBS = (
    "fia/test_*.py",
    "fia_backtest_*/*test*.py",
    "fia_final_cockpit/test_*.py",
    "fia_forward_oos/test_*.py",
    "phase21_live_engine_smoke_test.py",
    "test_reseal_refuses_any_observation_v672.py",
    "clear_nasdaq_brain/tests/run_all.py",
)

PER_ENTRY_TIMEOUT = 900

FAILING_STATUSES = (
    "FAIL",
    "PROJECT_IMPORT_DEFECT",
    "MISSING_FIXTURE_OR_DATA",
    "TIMEOUT",
    "TRUE_EXTERNAL_ENV_BLOCK",
)
NOT_TESTED_STATUSES = ("MISSING_EXTERNAL_DATA",)

_EXC_LINE = re.compile(r"^(?P<type>[A-Za-z_][A-Za-z0-9_.]*Error|SystemExit|KeyboardInterrupt)"
                       r"(?::\s*(?P<msg>.*))?$")
_NO_MODULE = re.compile(r"No module named ['\"]([^'\"]+)['\"]")
_CANNOT_IMPORT = re.compile(r"cannot import name ['\"][^'\"]+['\"] from ['\"]([^'\"]+)['\"]")
_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<fn>.*)$')
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_external_data_registry():
    """Validate external-data declarations and resolve their current identity.

    This registry is CI metadata only. It cannot grant scientific credit. A
    present file must match exact pinned size+SHA; a missing file remains missing.
    """
    errors = []
    datasets = {}
    entry_map = {}
    try:
        raw = json.loads(EXTERNAL_DATA_REGISTRY.read_text(encoding="utf-8"))
    except Exception as error:
        return {
            "valid": False,
            "errors": [f"registry unreadable: {type(error).__name__}: {error}"],
            "datasets": {},
            "entry_map": {},
        }

    if raw.get("schema") != "FIA_EXTERNAL_DATA_REGISTRY_V1":
        errors.append("unexpected registry schema")
    rows = raw.get("datasets")
    if not isinstance(rows, list) or not rows:
        errors.append("datasets must be a non-empty list")
        rows = []

    seen_ids = set()
    seen_entries = set()
    for row in rows:
        dataset_id = row.get("dataset_id")
        rel = row.get("canonical_repo_path")
        expected_size = row.get("expected_size")
        expected_sha = row.get("expected_sha256")
        required_by = row.get("required_by")

        if not isinstance(dataset_id, str) or not dataset_id or dataset_id in seen_ids:
            errors.append(f"invalid/duplicate dataset_id: {dataset_id!r}")
            continue
        seen_ids.add(dataset_id)
        if not isinstance(rel, str) or not rel.startswith("backend/") or ".." in Path(rel).parts:
            errors.append(f"{dataset_id}: invalid canonical_repo_path")
            continue
        if not isinstance(expected_size, int) or expected_size <= 0:
            errors.append(f"{dataset_id}: invalid expected_size")
        if not isinstance(expected_sha, str) or not _SHA256.fullmatch(expected_sha):
            errors.append(f"{dataset_id}: invalid expected_sha256")
        if row.get("scope") != "HISTORICAL_RESEARCH_ONLY":
            errors.append(f"{dataset_id}: scope must be HISTORICAL_RESEARCH_ONLY")
        if row.get("absence_status") != "MISSING_EXTERNAL_DATA":
            errors.append(f"{dataset_id}: absence status must be MISSING_EXTERNAL_DATA")
        if row.get("scientific_credit_when_absent") != "NONE":
            errors.append(f"{dataset_id}: absent dataset must grant no scientific credit")
        if row.get("predictive_validity_credit_when_absent") is not False:
            errors.append(f"{dataset_id}: predictive credit must be false")
        if row.get("forward_oos_credit_when_absent") is not False:
            errors.append(f"{dataset_id}: Forward-OOS credit must be false")
        if not isinstance(required_by, list) or not required_by:
            errors.append(f"{dataset_id}: required_by must be non-empty")
            required_by = []

        path = REPO_ROOT / rel
        if path.is_file():
            actual_size = path.stat().st_size
            actual_sha = _sha256(path)
            if actual_size == expected_size and actual_sha == expected_sha:
                state = "PRESENT_VERIFIED"
            else:
                state = "PRESENT_IDENTITY_MISMATCH"
                errors.append(
                    f"{dataset_id}: present bytes mismatch pinned identity "
                    f"(size={actual_size}, sha256={actual_sha})"
                )
        else:
            actual_size = None
            actual_sha = None
            state = "MISSING_EXTERNAL_DATA"

        dataset_record = {
            "dataset_id": dataset_id,
            "canonical_repo_path": rel,
            "expected_size": expected_size,
            "expected_sha256": expected_sha,
            "state": state,
            "actual_size": actual_size,
            "actual_sha256": actual_sha,
            "scope": row.get("scope"),
            "scientific_credit_when_absent": row.get("scientific_credit_when_absent"),
            "predictive_validity_credit_when_absent": row.get("predictive_validity_credit_when_absent"),
            "forward_oos_credit_when_absent": row.get("forward_oos_credit_when_absent"),
        }
        datasets[dataset_id] = dataset_record

        for req in required_by:
            entry = req.get("entry")
            baseline_status = req.get("baseline_failure_status")
            fragment = req.get("required_output_fragment")
            if (not isinstance(entry, str) or not entry or entry in seen_entries or
                    baseline_status not in FAILING_STATUSES or
                    not isinstance(fragment, str) or not fragment):
                errors.append(f"{dataset_id}: invalid/duplicate required_by declaration {req!r}")
                continue
            seen_entries.add(entry)
            entry_map[entry] = {
                "dataset_id": dataset_id,
                "baseline_failure_status": baseline_status,
                "required_output_fragment": fragment,
            }

    return {
        "valid": not errors,
        "errors": errors,
        "datasets": datasets,
        "entry_map": entry_map,
    }


def apply_external_data_contract(entry, status, evidence, output, registry):
    """Convert only exact registered absence failures to NOT_TESTED.

    If the dataset is absent but its associated check unexpectedly returns PASS,
    that is fail-open behavior and is promoted to FAIL rather than accepted.
    """
    req = registry.get("entry_map", {}).get(entry)
    if not req:
        return status, evidence
    dataset = registry.get("datasets", {}).get(req["dataset_id"], {})
    state = dataset.get("state")

    if state == "PRESENT_IDENTITY_MISMATCH":
        return "FAIL", {
            "reason": "registered external dataset is present but does not match pinned identity",
            "dataset": dataset,
            "original_status": status,
        }
    if state == "PRESENT_VERIFIED":
        return status, evidence
    if state != "MISSING_EXTERNAL_DATA":
        return status, evidence

    if status == "PASS":
        return "FAIL", {
            "reason": "check passed even though its declared required external dataset is absent",
            "dataset": dataset,
            "original_status": status,
        }

    fragment = req["required_output_fragment"]
    if status != req["baseline_failure_status"] or fragment not in output:
        return status, evidence

    return "MISSING_EXTERNAL_DATA", {
        "reason": "canonical historical external data absent; check is NOT_TESTED, not PASS",
        "dataset_id": dataset.get("dataset_id"),
        "canonical_repo_path": dataset.get("canonical_repo_path"),
        "expected_size": dataset.get("expected_size"),
        "expected_sha256": dataset.get("expected_sha256"),
        "scope": dataset.get("scope"),
        "scientific_credit": "NONE",
        "predictive_validity_credit": False,
        "forward_oos_credit": False,
        "original_status": status,
        "original_evidence": evidence,
    }


def discover():
    seen = set()
    for pattern in ENTRY_GLOBS:
        seen.update(glob.glob(pattern, root_dir=str(BACKEND)))
    return sorted(seen)


def last_exception(text):
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
    top = module.split(".")[0]
    if not top:
        return False
    return (BACKEND / top).is_dir() or (BACKEND / f"{top}.py").is_file()


def is_importable(module):
    top = module.split(".")[0]
    probe = (
        "import importlib.util, sys\n"
        f"sys.exit(0 if importlib.util.find_spec({top!r}) else 1)\n"
    )
    try:
        done = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True,
            timeout=60, cwd=str(BACKEND),
        )
    except Exception:
        return False
    return done.returncode == 0


def classify(returncode, output, timed_out):
    if timed_out:
        return "TIMEOUT", {"reason": f"exceeded {PER_ENTRY_TIMEOUT}s"}
    if returncode == 0:
        return "PASS", {}

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
                evidence["reason"] = f"{module!r} exists in this repository; the import failed anyway"
                return "PROJECT_IMPORT_DEFECT", evidence
            evidence["importable"] = is_importable(module)
            if not evidence["importable"]:
                evidence["reason"] = f"{module!r} is not in this repository and this interpreter cannot resolve it"
                return "TRUE_EXTERNAL_ENV_BLOCK", evidence
            evidence["reason"] = f"{module!r} IS importable; failure is in how the entry imports it"
            return "PROJECT_IMPORT_DEFECT", evidence
        evidence["reason"] = "import error naming no external module"
        return "PROJECT_IMPORT_DEFECT", evidence

    if exc_type in ("FileNotFoundError", "IsADirectoryError", "NotADirectoryError"):
        evidence["reason"] = "imports resolved; a required input was absent"
        return "MISSING_FIXTURE_OR_DATA", evidence

    if exc_type is None:
        printed = [line.strip() for line in output.strip().splitlines() if line.strip()]
        evidence["printed_failure"] = printed[-5:]
        evidence["reason"] = "non-zero exit with no traceback; check reported its own failure"
        return "FAIL", evidence

    evidence["reason"] = "non-zero exit after imports resolved"
    return "FAIL", evidence


def git_dirty(repo_root):
    done = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=str(repo_root))
    return sorted(line.strip() for line in done.stdout.splitlines() if line.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    registry = load_external_data_registry()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(BACKEND)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))

    entries = discover()
    baseline_dirty = git_dirty(repo_root)
    results = {}
    seen_dirty = set(baseline_dirty)

    for entry in entries:
        timed_out = False
        try:
            done = subprocess.run(
                [sys.executable, entry], capture_output=True, text=True,
                timeout=PER_ENTRY_TIMEOUT, cwd=str(BACKEND), env=env,
            )
            returncode = done.returncode
            output = (done.stdout or "") + (done.stderr or "")
        except subprocess.TimeoutExpired as expired:
            timed_out = True
            returncode = None
            output = (expired.stdout or "") + (expired.stderr or "") if isinstance(expired.stdout, str) else ""

        status, evidence = classify(returncode, output, timed_out)
        status, evidence = apply_external_data_contract(entry, status, evidence, output, registry)

        now_dirty = set(git_dirty(repo_root))
        introduced = sorted(now_dirty - seen_dirty)
        seen_dirty |= now_dirty
        record = {"status": status, "evidence": evidence}
        if introduced:
            record["mutated_tracked_files"] = introduced
        if status != "PASS":
            record["output_tail"] = output.strip().splitlines()[-25:]
        results[entry] = record
        print(f"{status:<24} {entry}", flush=True)

    counts = {}
    for record in results.values():
        counts[record["status"]] = counts.get(record["status"], 0) + 1

    payload = {
        "schema": "FIA_SUITE_RESULT_V3",
        "entry_count": len(entries),
        "counts": counts,
        "baseline_dirty": baseline_dirty,
        "mutated_by_suite": sorted(seen_dirty - set(baseline_dirty)),
        "external_data_registry": registry,
        "results": results,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print("\nCOUNTS " + json.dumps(counts, sort_keys=True))
    print("EXTERNAL_DATA_REGISTRY_VALID", registry["valid"])
    for error in registry["errors"]:
        print("EXTERNAL_DATA_REGISTRY_ERROR", error)
    for entry, record in sorted(results.items()):
        if record["status"] == "PASS":
            continue
        evidence = record["evidence"]
        print(f"\n--- {record['status']}  {entry}")
        if evidence.get("exception_type"):
            print(f"    exception : {evidence.get('exception_type')}: {evidence.get('exception_message')}")
            print(f"    frame     : {evidence.get('final_frame')}")
        for line in evidence.get("printed_failure", []):
            print(f"    reported  : {line}")
        print(f"    reason    : {evidence.get('reason')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
