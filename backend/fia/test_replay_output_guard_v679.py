# CLEAR NASDAQ — v679: every replay/backtest runner routes canonical output
# through the A6 artifact guard.
#
# WHY THIS EXISTS
# ---------------
# A6 registered 106 canonical artifacts and redirected guarded writes to
# backend/.artifact_runs/<run>/, then verified empirically that the suite
# mutated none of them. That verification ran in a sandbox where
# fia_backtest_phase19 and fia_backtest_phase21 died at import before writing
# anything, so those two runners could never have been observed mutating. They
# were never wired to the guard.
#
# The moment the runner's sys.path defect was fixed and they actually executed,
# they rewrote four registered artifacts:
#
#   fia_backtest_phase19/results/phase19_full_backtest.csv
#   fia_backtest_phase19/results/phase19_full_backtest_summary.json
#   fia_backtest_phase21/results/phase21_no_neutral_backtest_1y.csv
#   fia_backtest_phase21/results/phase21_no_neutral_backtest_1y_summary.json
#
# The guard is opt-in: a runner is protected only if it calls
# guarded_output_path() before writing. Nothing enforced that, so the guarantee
# held only for the runners someone had remembered to wire up.
#
# This check closes that gap structurally. It asserts the property for every
# runner that writes a registered artifact, so a NEW runner cannot reintroduce
# the same hole, and it does so without re-recording or blessing any bytes.
#
# WHAT IS DELIBERATELY NOT DONE HERE
# ----------------------------------
#  * No expected hash is updated and no artifact is re-registered. A mismatch
#    stays evidence, per the registry's own note.
#  * No scientific behaviour is touched. The redirect changes WHERE a result is
#    written, never what the result is.
from __future__ import annotations

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia.artifact_guard import (  # noqa: E402
    guarded_output_path,
    is_protected,
    protected_relpaths,
    run_dir,
)

GUARD_FUNCTION = "guarded_output_path"

failures = []
checks = 0


def check(label, condition):
    global checks
    checks += 1
    if condition:
        print(f"PASS  {label}")
    else:
        print(f"FAIL  {label}")
        failures.append(label)


def runner_files():
    """Every executable runner under a backtest/replay package."""
    found = []
    for directory in sorted(BACKEND.glob("fia_backtest_*")):
        if not directory.is_dir():
            continue
        found.extend(sorted(directory.rglob("*.py")))
    return found


def literal_output_paths(path):
    """Module-level path constants a runner assigns, resolved to relpaths.

    Only literal assignments are read. A runner that computes its output path
    dynamically is not covered by this scan, which is why the redirect property
    is also asserted directly against the guard below.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return {}

    constants = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        rendered = render_path(node.value, constants)
        if rendered:
            constants[target.id] = rendered
    return constants


def write_sites(path, constants):
    """Split a module's path constants into (written raw, written via guard).

    Two distinctions matter and both are easy to get wrong.

    First, naming a registered artifact is not a violation. Most modules that
    mention one are reading it as input, and flagging reads would make this
    check noisy enough to be ignored. Only writes can mutate evidence.

    Second, the check must not go vacuous once the fix is applied. Wrapping a
    write as guarded_output_path(CONST).write_text(...) removes CONST from the
    write site, so a scan that only looked for raw writes would report "no
    offenders" both when every writer is guarded AND when no writer is
    detected at all. Guarded writes are therefore collected separately and used
    to prove the scan still sees the writers it is meant to police.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set(), set()

    written = set()
    guarded = set()

    # Any constant handed to the guard counts as a guarded write target,
    # including via an intermediate local (csv_target = guarded_output_path(X)).
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == GUARD_FUNCTION:
            for arg in node.args:
                if isinstance(arg, ast.Name) and arg.id in constants:
                    guarded.add(constants[arg.id])

    def mode_is_write(args, keywords):
        for arg in args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return any(flag in arg.value for flag in ("w", "a", "x", "+"))
        for keyword in keywords:
            if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                return any(flag in str(keyword.value.value)
                           for flag in ("w", "a", "x", "+"))
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func

        # NAME.write_text(...) / NAME.write_bytes(...) / NAME.open("w") / NAME.to_csv(...)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            name = func.value.id
            if name not in constants:
                continue
            if func.attr in ("write_text", "write_bytes", "to_csv", "to_json"):
                written.add(constants[name])
            elif func.attr == "open" and mode_is_write(node.args, node.keywords):
                written.add(constants[name])

        # open(NAME, "w") / gzip.open(NAME, "wt")
        elif (isinstance(func, ast.Name) and func.id == "open") or \
             (isinstance(func, ast.Attribute) and func.attr == "open"):
            if node.args and isinstance(node.args[0], ast.Name):
                name = node.args[0].id
                if name in constants and mode_is_write(node.args[1:], node.keywords):
                    written.add(constants[name])

    return written, guarded


def render_path(node, constants):
    """Render Path("a") and Path("a") / "b" / "c" into a relative string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id == "Path" and len(node.args) == 1:
        return render_path(node.args[0], constants)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = render_path(node.left, constants)
        right = render_path(node.right, constants)
        if left and right:
            return f"{left}/{right}"
    return None


print("=" * 66)
print("V679 — REPLAY OUTPUT GUARD COVERAGE")
print("=" * 66)

# 1. The guard itself still redirects a registered artifact away from canonical.
print("\n[1] THE GUARD REDIRECTS REGISTERED ARTIFACTS")
sample = protected_relpaths()[0]
redirected = guarded_output_path(BACKEND / sample)
check("a registered artifact is redirected off its canonical path",
      redirected != (BACKEND / sample))
check("the redirect lands inside the per-run directory",
      str(redirected).startswith(str(run_dir())))
check("an unregistered path passes through untouched",
      guarded_output_path(BACKEND / "not_registered_xyz.tmp")
      == BACKEND / "not_registered_xyz.tmp")

# 2. Every runner whose literal output constants name a registered artifact
#    must import and call the guard. This is the property that was violated.
print("\n[2] EVERY RUNNER WRITING A REGISTERED ARTIFACT USES THE GUARD")
offenders = []
covered = []
for runner in runner_files():
    constants = literal_output_paths(runner)
    raw, guarded = write_sites(runner, constants)
    raw_protected = sorted(r for r in raw if is_protected(BACKEND / r))
    guarded_protected = sorted(r for r in guarded if is_protected(BACKEND / r))
    if not raw_protected and not guarded_protected:
        continue
    rel_runner = str(runner.relative_to(BACKEND))
    if raw_protected:
        offenders.append((rel_runner, raw_protected))
    if guarded_protected:
        covered.append(rel_runner)

for name in covered:
    print(f"      guarded: {name}")
for name, artifacts in offenders:
    print(f"      UNGUARDED: {name}")
    for artifact in artifacts:
        print(f"                 writes {artifact}")

check("at least one runner was scanned (the scan is not vacuous)",
      bool(covered or offenders))
check("no runner writes a registered artifact without the guard",
      not offenders)

# 3. The four artifacts that were actually mutated are registered, and the
#    runners responsible are now wired up. Named explicitly so a silent
#    unregistration cannot make this check pass by making them unprotected.
print("\n[3] THE FOUR PREVIOUSLY MUTATED ARTIFACTS")
REGRESSED = {
    "fia_backtest_phase19/results/phase19_full_backtest.csv":
        "fia_backtest_phase19/full_backtest.py",
    "fia_backtest_phase19/results/phase19_full_backtest_summary.json":
        "fia_backtest_phase19/full_backtest.py",
    "fia_backtest_phase21/results/phase21_no_neutral_backtest_1y.csv":
        "fia_backtest_phase21/full_backtest.py",
    "fia_backtest_phase21/results/phase21_no_neutral_backtest_1y_summary.json":
        "fia_backtest_phase21/full_backtest.py",
}
for artifact, runner in REGRESSED.items():
    check(f"still registered: {artifact}", is_protected(BACKEND / artifact))
    check(f"redirected away from canonical: {artifact}",
          guarded_output_path(BACKEND / artifact) != BACKEND / artifact)
    source = (BACKEND / runner).read_text(encoding="utf-8", errors="replace")
    check(f"{runner} calls the guard", GUARD_FUNCTION in source)

# The point-in-time variant shares phase 19's output paths and must be wired
# up too, or one of the two runners would still write canonically.
VARIANT = "fia_backtest_phase19/full_backtest.before_earnings_pti.py"
variant_source = (BACKEND / VARIANT).read_text(encoding="utf-8", errors="replace")
check(f"{VARIANT} calls the guard", GUARD_FUNCTION in variant_source)

print("\n" + "=" * 66)
if failures:
    print(f"FAILED {len(failures)} of {checks} check(s):")
    for label in failures:
        print(f"   - {label}")
    raise SystemExit(1)
print(f"V679 REPLAY OUTPUT GUARD COVERAGE PASS  ({checks} checks)")
print("=" * 66)
