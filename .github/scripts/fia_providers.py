# CLEAR NASDAQ — explicit identification of provider-dependent checks (CI harness only)
#
# WHY
# ---
# A providers.py split must be proven not to change behaviour, so the baseline
# has to name, in advance and by evidence, exactly which checks exercise
# providers.py at all. "The provider tests" as a remembered count is not a
# baseline; a list derived from the source is.
#
# Detection walks the first-party import graph rather than grepping test files.
# A check that imports fia.engine, which imports fia.providers, exercises the
# provider surface just as surely as one that names ProviderHub directly, and a
# grep would miss it.
#
# This file is deliberately outside backend/ for the same reason as fia_suite.py:
# files under the backend root are fingerprinted against an explicit registry and
# an unclassified one is a hard error.
from __future__ import annotations

import argparse
import ast
import glob
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"

TARGET = "fia.providers"

ENTRY_GLOBS = (
    "fia/test_*.py",
    "fia_backtest_*/*test*.py",
    "fia_final_cockpit/test_*.py",
    "fia_forward_oos/test_*.py",
    "phase21_live_engine_smoke_test.py",
    "test_reseal_refuses_any_observation_v672.py",
    "clear_nasdaq_brain/tests/run_all.py",
)


def discover():
    seen = set()
    for pattern in ENTRY_GLOBS:
        seen.update(glob.glob(pattern, root_dir=str(BACKEND)))
    return sorted(seen)


def module_name(path):
    relative = Path(path).with_suffix("")
    return ".".join(relative.parts)


def resolve(module):
    """Map a dotted first-party module to a file under the backend root."""
    as_module = BACKEND / (module.replace(".", "/") + ".py")
    if as_module.is_file():
        return as_module
    as_package = BACKEND / module.replace(".", "/") / "__init__.py"
    if as_package.is_file():
        return as_package
    return None


def imports_of(path):
    """First-party dotted imports named by one file, relative imports resolved."""
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()

    package = ".".join(Path(path).relative_to(BACKEND).parts[:-1])
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package
                for _ in range(node.level - 1):
                    base = base.rpartition(".")[0]
                head = f"{base}.{node.module}" if node.module else base
            else:
                head = node.module or ""
            if head:
                found.add(head)
                for alias in node.names:
                    found.add(f"{head}.{alias.name}")
    return found


def reaches_target(entry):
    """Walk the first-party import graph from one entry looking for the target."""
    start = BACKEND / entry
    queue = [start]
    visited = {start}
    path_to = {start: [entry]}

    while queue:
        current = queue.pop()
        for name in imports_of(current):
            if name == TARGET or name.startswith(TARGET + "."):
                return True, path_to[current] + [TARGET]
            resolved = resolve(name)
            if resolved and resolved not in visited:
                visited.add(resolved)
                path_to[resolved] = path_to[current] + [name]
                queue.append(resolved)
    return False, []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    provider_entries = {}
    for entry in discover():
        hit, chain = reaches_target(entry)
        if hit:
            provider_entries[entry] = {
                "direct": len(chain) == 2,
                "import_chain": chain,
            }

    payload = {
        "schema": "FIA_PROVIDER_SCOPE_V1",
        "target": TARGET,
        "count": len(provider_entries),
        "entries": provider_entries,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"PROVIDER-DEPENDENT CHECKS: {len(provider_entries)}")
    for entry, info in sorted(provider_entries.items()):
        kind = "direct  " if info["direct"] else "indirect"
        print(f"  {kind} {entry}")
        if not info["direct"]:
            print(f"           via {' -> '.join(info['import_chain'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
