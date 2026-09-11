# CLEAR NASDAQ — final CI gate (harness only)
#
# WHY
# ---
# Previously the suite step decided the build by calling SystemExit(1) the moment
# it disliked the counts. Everything after it was skipped, so a failing suite
# meant the two checks that actually protect the evidence base — protected
# artifacts byte-identical across the whole run, and a clean working tree — never
# ran at all. The run reported the failure it happened to notice first and stayed
# silent about the two questions that matter most.
#
# Reporting and adjudication are now separate. Each earlier step records what it
# observed and exits 0. This gate reads every record and decides once, so a red
# suite can no longer hide an artifact mutation behind it.
#
# This gate never downgrades a failure. It exists to make MORE evidence visible,
# not to let any of it pass.
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

# A provider-dependent check that never reached its assertions proves nothing
# about a providers.py split, so it is not allowed to count as coverage.
NOT_EXECUTED = ("TRUE_EXTERNAL_ENV_BLOCK", "PROJECT_IMPORT_DEFECT")


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as error:
        return {"_unreadable": f"{type(error).__name__}: {error}"}


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

    # 1. Every record must exist. A missing one means a step died without
    #    reporting, which is itself a failure rather than an absence of news.
    for name, record in (
        ("suite", suite), ("artifacts", artifacts),
        ("worktree", worktree), ("providers", providers),
    ):
        if "_unreadable" in record:
            gates.append((f"record:{name}", False, record["_unreadable"]))
        else:
            gates.append((f"record:{name}", True, "present"))

    counts = suite.get("counts", {}) if "_unreadable" not in suite else {}

    # 2. Dependencies. CI installs and verifies the declared set, so a genuine
    #    external block here means the environment is not what it claims.
    env_blocked = counts.get("TRUE_EXTERNAL_ENV_BLOCK", 0)
    gates.append((
        "dependencies", env_blocked == 0,
        f"TRUE_EXTERNAL_ENV_BLOCK={env_blocked}",
    ))

    # 3. Suite outcome.
    failing = sum(counts.get(status, 0) for status in FAILING_STATUSES)
    gates.append((
        "suite", failing == 0,
        f"{counts.get('PASS', 0)} pass, {failing} failing of "
        f"{suite.get('entry_count', '?')}",
    ))

    # 4. Protected artifacts, compared across the WHOLE run.
    if "_unreadable" not in artifacts:
        changed = artifacts.get("changed", [])
        ok = bool(artifacts.get("verify_ok")) and not changed
        gates.append((
            "protected_artifacts", ok,
            f"{artifacts.get('count', '?')} registered, {len(changed)} changed, "
            f"verify_ok={artifacts.get('verify_ok')}",
        ))

    # 5. Working tree. Anything the suite wrote to a tracked file shows here,
    #    whether or not the registry happens to protect it.
    if "_unreadable" not in worktree:
        modified = worktree.get("modified", worktree.get("dirty", []))
        untracked = worktree.get("untracked", [])
        gates.append((
            "working_tree", not modified and not untracked,
            f"{len(modified)} tracked file(s) modified, "
            f"{len(untracked)} untracked file(s) left",
        ))

    # 6. Provider coverage.
    if "_unreadable" not in providers and "_unreadable" not in suite:
        results = suite.get("results", {})
        not_run = sorted(
            entry for entry in providers.get("entries", {})
            if results.get(entry, {}).get("status") in NOT_EXECUTED
        )
        gates.append((
            "provider_coverage", not not_run,
            f"{providers.get('count', 0)} provider-dependent checks, "
            f"{len(not_run)} did not execute",
        ))

    width = max(len(name) for name, _, _ in gates)
    print("=" * 70)
    print("FIA VERIFY — FINAL GATE")
    print("=" * 70)
    for name, ok, detail in gates:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")

    if "_unreadable" not in worktree:
        for label, key in (("modified by", "modified"), ("left untracked by", "untracked")):
            paths = worktree.get(key) or []
            if paths:
                print(f"\n  files {label} the suite:")
                for path in paths:
                    print(f"    {path}")

    if "_unreadable" not in suite:
        for entry, record in sorted(suite.get("results", {}).items()):
            if record["status"] in FAILING_STATUSES:
                evidence = record.get("evidence", {})
                print(f"\n  {record['status']}  {entry}")
                if evidence.get("exception_type"):
                    print(f"      {evidence.get('exception_type')}: "
                          f"{evidence.get('exception_message')}")
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
