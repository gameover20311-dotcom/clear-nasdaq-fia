# CLEAR NASDAQ — final CI gate (harness only)
#
# Reporting and adjudication are separate.  Every upstream record is treated as
# untrusted input: a missing, empty, partial or internally inconsistent result
# must fail closed rather than manufacture a green release gate.
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
VALID_STATUSES = {"PASS", *FAILING_STATUSES}
NOT_EXECUTED = ("TRUE_EXTERNAL_ENV_BLOCK", "PROJECT_IMPORT_DEFECT")
SUITE_SCHEMA = "FIA_SUITE_RESULT_V3"


def load(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"_unreadable": "top-level JSON is not an object"}
    except Exception as error:
        return {"_unreadable": f"{type(error).__name__}: {error}"}


def _suite_integrity(suite):
    """Return (ok, detail, recalculated_counts).

    This closes the previous fail-open condition where `{counts:{},results:{}}`
    and even missing provider entries could be accepted as PASS.
    """
    issues = []
    if suite.get("schema") != SUITE_SCHEMA:
        issues.append(f"schema={suite.get('schema')!r}, expected {SUITE_SCHEMA}")

    entry_count = suite.get("entry_count")
    results = suite.get("results")
    counts = suite.get("counts")
    if not isinstance(entry_count, int) or isinstance(entry_count, bool) or entry_count <= 0:
        issues.append(f"invalid entry_count={entry_count!r}")
    if not isinstance(results, dict) or not results:
        issues.append("results missing or empty")
        results = {}
    if isinstance(entry_count, int) and not isinstance(entry_count, bool) and len(results) != entry_count:
        issues.append(f"results cardinality {len(results)} != entry_count {entry_count}")
    if not isinstance(counts, dict):
        issues.append("counts missing or not an object")
        counts = {}

    recalculated = {}
    for entry, record in results.items():
        if not isinstance(entry, str) or not entry:
            issues.append("result contains invalid entry name")
            continue
        if not isinstance(record, dict):
            issues.append(f"{entry}: result record is not an object")
            continue
        status = record.get("status")
        if status not in VALID_STATUSES:
            issues.append(f"{entry}: unknown status {status!r}")
            continue
        recalculated[status] = recalculated.get(status, 0) + 1
        evidence = record.get("evidence")
        if not isinstance(evidence, dict):
            issues.append(f"{entry}: evidence missing or not an object")
        elif status == "PASS" and evidence.get("executed") is not True:
            issues.append(f"{entry}: PASS lacks executed=true evidence")
        if record.get("mutated_tracked_files") and status == "PASS":
            # A scientific check that mutates tracked bytes may still have found
            # its assertions true, but the release record is not clean evidence.
            issues.append(f"{entry}: PASS mutated tracked files")

    for key, value in counts.items():
        if key not in VALID_STATUSES or not isinstance(value, int) or isinstance(value, bool) or value < 0:
            issues.append(f"invalid count {key!r}={value!r}")
    if {k: v for k, v in counts.items() if v} != {k: v for k, v in recalculated.items() if v}:
        issues.append(f"counts/results mismatch declared={counts} recalculated={recalculated}")
    if sum(recalculated.values()) != len(results):
        issues.append("not every result has a valid classified status")

    return not issues, ("; ".join(issues) if issues else f"{entry_count} complete classified entries"), recalculated


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

    suite_ok = False
    recalculated = {}
    if "_unreadable" not in suite:
        suite_ok, detail, recalculated = _suite_integrity(suite)
        gates.append(("suite_evidence_integrity", suite_ok, detail))

    # Dependencies and outcome only make sense for a structurally valid suite.
    if suite_ok:
        env_blocked = recalculated.get("TRUE_EXTERNAL_ENV_BLOCK", 0)
        gates.append(("dependencies", env_blocked == 0,
                      f"TRUE_EXTERNAL_ENV_BLOCK={env_blocked}"))
        failing = sum(recalculated.get(status, 0) for status in FAILING_STATUSES)
        gates.append(("suite", failing == 0,
                      f"{recalculated.get('PASS', 0)} pass, {failing} failing of {suite['entry_count']}"))
    else:
        gates.append(("dependencies", False, "suite evidence invalid"))
        gates.append(("suite", False, "suite evidence invalid"))

    # Protected artifacts record must itself have the required fields.
    if "_unreadable" not in artifacts:
        changed = artifacts.get("changed")
        count = artifacts.get("count")
        shape_ok = isinstance(changed, list) and isinstance(count, int) and not isinstance(count, bool) and count > 0
        ok = shape_ok and artifacts.get("verify_ok") is True and not changed
        gates.append(("protected_artifacts", ok,
                      f"shape_ok={shape_ok}, {count!r} registered, "
                      f"{len(changed) if isinstance(changed, list) else '?'} changed, "
                      f"verify_ok={artifacts.get('verify_ok')}"))

    # Working tree record must explicitly provide lists rather than silently
    # defaulting absent fields to a clean tree.
    if "_unreadable" not in worktree:
        modified = worktree.get("modified", worktree.get("dirty"))
        untracked = worktree.get("untracked")
        shape_ok = isinstance(modified, list) and isinstance(untracked, list)
        gates.append(("working_tree", shape_ok and not modified and not untracked,
                      f"shape_ok={shape_ok}, "
                      f"{len(modified) if isinstance(modified, list) else '?'} tracked modified, "
                      f"{len(untracked) if isinstance(untracked, list) else '?'} untracked"))

    # Every ACTIVE provider-dependent check must exist in suite results and must
    # have executed. Historical-only forensic baselines are intentionally kept in
    # the provider inventory but are not current-code PASS gates; fia_suite.py
    # records that exclusion explicitly and requires active replacement checks.
    # Counting a historical-only baseline as a missing active check creates a
    # false provider-coverage failure, so consume the suite's declared exclusion
    # list here rather than maintaining a second hard-coded copy.
    if "_unreadable" not in providers and suite_ok:
        entries = providers.get("entries")
        results = suite["results"]
        historical_only = suite.get("historical_only_entries")
        historical_shape_ok = (
            isinstance(historical_only, list)
            and all(isinstance(entry, str) and entry for entry in historical_only)
        )
        if not isinstance(entries, dict) or not entries:
            gates.append(("provider_coverage", False, "provider inventory missing or empty"))
        elif not historical_shape_ok:
            gates.append(("provider_coverage", False, "historical-only suite metadata missing or invalid"))
        else:
            historical = set(historical_only)
            active_entries = {entry: info for entry, info in entries.items() if entry not in historical}
            excluded = sorted(entry for entry in entries if entry in historical)
            missing = sorted(entry for entry in active_entries if entry not in results)
            not_run = sorted(entry for entry in active_entries
                             if entry in results and results[entry].get("status") in NOT_EXECUTED)
            gates.append(("provider_coverage", not missing and not not_run,
                          f"{len(active_entries)} active expected of {len(entries)} inventory; "
                          f"{len(excluded)} historical-only excluded; "
                          f"{len(missing)} missing; {len(not_run)} did not execute"))
    elif "_unreadable" not in providers:
        gates.append(("provider_coverage", False, "suite evidence invalid"))

    width = max(len(name) for name, _, _ in gates)
    print("=" * 70)
    print("FIA VERIFY — FINAL GATE")
    print("=" * 70)
    for name, ok, detail in gates:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")

    if "_unreadable" not in worktree:
        for label, key in (("modified by", "modified"), ("left untracked by", "untracked")):
            paths = worktree.get(key) or []
            if isinstance(paths, list) and paths:
                print(f"\n  files {label} the suite:")
                for path in paths:
                    print(f"    {path}")

    if suite_ok:
        for entry, record in sorted(suite["results"].items()):
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
    print("RESULT: PASS — all gates green")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
