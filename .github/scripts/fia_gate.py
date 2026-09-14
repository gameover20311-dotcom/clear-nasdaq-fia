# CLEAR NASDAQ — final CI gate (harness only)
#
# Reporting and adjudication are separate. The gate never converts unavailable
# historical data into PASS. Exact registered canonical external data may be
# reported MISSING_EXTERNAL_DATA / NOT_TESTED with zero scientific, predictive,
# Forward-OOS, or provider-execution coverage credit. Any undeclared missing
# input, wrong bytes, fail-open check, code failure, environment block, mutation,
# or protected-artifact change remains fatal.
from __future__ import annotations

import argparse
import json
from pathlib import Path

FAILING_STATUSES = (
    "FAIL",
    "PROJECT_IMPORT_DEFECT",
    "MISSING_FIXTURE_OR_DATA",
    "TIMEOUT",
    "TRUE_EXTERNAL_ENV_BLOCK",
)
NOT_TESTED_STATUSES = ("MISSING_EXTERNAL_DATA",)
HARD_NOT_EXECUTED = ("TRUE_EXTERNAL_ENV_BLOCK", "PROJECT_IMPORT_DEFECT")
NO_COVERAGE_STATUSES = ("MISSING_EXTERNAL_DATA",)


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as error:
        return {"_unreadable": f"{type(error).__name__}: {error}"}


def validate_external_not_tested(suite):
    """Prove every MISSING_EXTERNAL_DATA is exact, declared, and creditless."""
    reg = suite.get("external_data_registry") or {}
    errors = list(reg.get("errors") or [])
    if not reg.get("valid"):
        errors.append("external-data registry is not valid")

    datasets = reg.get("datasets") or {}
    entry_map = reg.get("entry_map") or {}
    results = suite.get("results") or {}

    not_tested = []
    for entry, record in results.items():
        if record.get("status") != "MISSING_EXTERNAL_DATA":
            continue
        not_tested.append(entry)
        req = entry_map.get(entry)
        if not req:
            errors.append(f"{entry}: MISSING_EXTERNAL_DATA without registry declaration")
            continue
        dataset = datasets.get(req.get("dataset_id")) or {}
        ev = record.get("evidence") or {}
        if dataset.get("state") != "MISSING_EXTERNAL_DATA":
            errors.append(f"{entry}: dataset state is not missing")
        if ev.get("dataset_id") != dataset.get("dataset_id"):
            errors.append(f"{entry}: evidence dataset identity mismatch")
        if ev.get("expected_size") != dataset.get("expected_size"):
            errors.append(f"{entry}: expected size mismatch")
        if ev.get("expected_sha256") != dataset.get("expected_sha256"):
            errors.append(f"{entry}: expected sha256 mismatch")
        if ev.get("scientific_credit") != "NONE":
            errors.append(f"{entry}: missing data granted scientific credit")
        if ev.get("predictive_validity_credit") is not False:
            errors.append(f"{entry}: missing data granted predictive-validity credit")
        if ev.get("forward_oos_credit") is not False:
            errors.append(f"{entry}: missing data granted Forward-OOS credit")

    for entry, req in entry_map.items():
        dataset = datasets.get(req.get("dataset_id")) or {}
        if dataset.get("state") != "MISSING_EXTERNAL_DATA":
            continue
        status = (results.get(entry) or {}).get("status")
        if status != "MISSING_EXTERNAL_DATA":
            errors.append(f"{entry}: required missing dataset but status={status!r}")

    return not errors, errors, sorted(not_tested)


def provider_execution_status(providers, results):
    """Separate hard non-execution from explicit external-data NOT_TESTED.

    MISSING_EXTERNAL_DATA is not a provider coverage success. It receives zero
    provider-execution credit, but when the external-data contract has already
    validated it as an expected canonical-data absence it is also not a code or
    environment regression. The final output must preserve that distinction.
    """
    entries = providers.get("entries", {}) if isinstance(providers, dict) else {}
    hard_not_run = sorted(
        entry for entry in entries
        if (results.get(entry) or {}).get("status") in HARD_NOT_EXECUTED
    )
    no_coverage = sorted(
        entry for entry in entries
        if (results.get(entry) or {}).get("status") in NO_COVERAGE_STATUSES
    )
    return hard_not_run, no_coverage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--providers", required=True)
    args = parser.parse_args()

    suite = load(args.suite)
    artifacts = load(args.artifacts)
    worktree = load(args.worktree)
    providers = load(args.providers)
    gates = []

    for name, record in (
        ("suite", suite), ("artifacts", artifacts),
        ("worktree", worktree), ("providers", providers),
    ):
        if "_unreadable" in record:
            gates.append((f"record:{name}", False, record["_unreadable"]))
        else:
            gates.append((f"record:{name}", True, "present"))

    counts = suite.get("counts", {}) if "_unreadable" not in suite else {}
    results = suite.get("results", {}) if "_unreadable" not in suite else {}

    env_blocked = counts.get("TRUE_EXTERNAL_ENV_BLOCK", 0)
    gates.append(("dependencies", env_blocked == 0, f"TRUE_EXTERNAL_ENV_BLOCK={env_blocked}"))

    external_ok, external_errors, not_tested_entries = (
        validate_external_not_tested(suite) if "_unreadable" not in suite
        else (False, ["suite unreadable"], [])
    )
    gates.append((
        "external_data_contract", external_ok,
        f"{len(not_tested_entries)} exact historical check(s) NOT_TESTED; "
        f"errors={len(external_errors)}",
    ))

    failing = sum(counts.get(status, 0) for status in FAILING_STATUSES)
    not_tested = sum(counts.get(status, 0) for status in NOT_TESTED_STATUSES)
    gates.append((
        "suite", failing == 0,
        f"{counts.get('PASS', 0)} pass, {failing} failing, {not_tested} NOT_TESTED "
        f"of {suite.get('entry_count', '?')}",
    ))

    if "_unreadable" not in artifacts:
        changed = artifacts.get("changed", [])
        ok = bool(artifacts.get("verify_ok")) and not changed
        gates.append((
            "protected_artifacts", ok,
            f"{artifacts.get('count', '?')} registered, {len(changed)} changed, "
            f"verify_ok={artifacts.get('verify_ok')}",
        ))

    if "_unreadable" not in worktree:
        modified = worktree.get("modified", worktree.get("dirty", []))
        untracked = worktree.get("untracked", [])
        gates.append((
            "working_tree", not modified and not untracked,
            f"{len(modified)} tracked file(s) modified, {len(untracked)} untracked file(s) left",
        ))

    if "_unreadable" not in providers and "_unreadable" not in suite:
        hard_not_run, no_coverage = provider_execution_status(providers, results)
        gates.append((
            "provider_coverage", not hard_not_run,
            f"{providers.get('count', 0)} provider-dependent checks; "
            f"{len(no_coverage)} explicit external NOT_TESTED with zero coverage credit; "
            f"{len(hard_not_run)} unexpectedly did not execute",
        ))

    width = max(len(name) for name, _, _ in gates)
    print("=" * 70)
    print("FIA VERIFY — FINAL GATE")
    print("=" * 70)
    for name, ok, detail in gates:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")

    if external_errors:
        print("\n  external-data contract errors:")
        for error in external_errors:
            print(f"    {error}")

    if not_tested_entries:
        print("\n  historical checks explicitly NOT_TESTED — zero scientific/predictive/Forward-OOS credit:")
        for entry in not_tested_entries:
            ev = results[entry].get("evidence", {})
            print(f"    {entry}  dataset={ev.get('dataset_id')}  expected_sha256={ev.get('expected_sha256')}")

    if "_unreadable" not in providers and "_unreadable" not in suite:
        _, no_coverage = provider_execution_status(providers, results)
        if no_coverage:
            print("\n  provider-dependent checks with zero execution-coverage credit:")
            for entry in no_coverage:
                print(f"    {entry}")

    if "_unreadable" not in worktree:
        for label, key in (("modified by", "modified"), ("left untracked by", "untracked")):
            paths = worktree.get(key) or []
            if paths:
                print(f"\n  files {label} the suite:")
                for path in paths:
                    print(f"    {path}")

    if "_unreadable" not in suite:
        for entry, record in sorted(results.items()):
            if record["status"] in FAILING_STATUSES:
                evidence = record.get("evidence", {})
                print(f"\n  {record['status']}  {entry}")
                if evidence.get("exception_type"):
                    print(f"      {evidence.get('exception_type')}: {evidence.get('exception_message')}")
                for line in evidence.get("printed_failure", []):
                    print(f"      reported: {line}")
                print(f"      {evidence.get('reason')}")

    failed = [name for name, ok, _ in gates if not ok]
    print("=" * 70)
    if failed:
        print("RESULT: FAIL — " + ", ".join(failed))
        print("=" * 70)
        return 1
    print("RESULT: PASS — executable gates green; NOT_TESTED historical checks remain explicitly uncredited")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
