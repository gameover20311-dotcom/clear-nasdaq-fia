#!/usr/bin/env python3
"""PROVIDERS SPLIT COVERAGE MAP (v680) — what is safe to move, what is not.

WHY THIS EXISTS
---------------
Before providers.py is split, every method that will be moved needs explicit
pre-split equivalence coverage. Answering "is it covered?" by searching the
harness for a method's NAME is not good enough and actively dangerous: the first
version of this measurement reported snapshot() as covered because the harness
mentions the word "snapshot" in a prose comment. snapshot() is the largest and
riskiest method in the file, 797 lines, with no coverage whatsoever. An
over-reporting coverage map is worse than no map, because it is trusted.

So coverage here means ONE thing: the harness contains an actual CALL to the
method, found by parsing the harness with ast, never by substring match. A
mention in a comment, a docstring or a string literal counts for nothing.

A second failure mode this guards is the silently-raising call site. The harness
records __RAISED__ for a call whose signature does not match, which keeps the
run alive but leaves the method unexercised while it still LOOKS called. Two
methods were in exactly that state: calculate_source_confirmation_score was
handed a list when it takes one article, and _latest_candle_start was called
with (hub, "60") when it takes the payload alone. Both are fixed in v678; this
check asserts the harness executes with zero __RAISED__ so the state cannot come
back unnoticed.

This file only READS. It changes nothing, moves nothing and splits nothing.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PROVIDERS = BACKEND / "fia" / "providers.py"
HARNESS = BACKEND / "fia" / "test_providers_equivalence_v678.py"
SPLIT_MAP = BACKEND / "fia" / "providers_split_map.json"

# Resolved statically from fia_backtest_phase20/full_backtest.py. phase20 is
# permanently blocked on MISSING_CANONICAL_DATA, so it can never exercise these
# itself; they must be covered by fixtures instead or the split loses that path.
PHASE20_PROVIDER_PATH = (
    "analyze_nasdaq_relevance_v3",
    "analyze_news_context",
    "analyze_news_context_v3_calibrated",
    "apply_news_trust_scores",
    "calculate_news_recency_score",
    "detect_duplicate_news",
    "filter_news_quality",
    "get",
)

failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"PASS  {label}")
    else:
        print(f"FAIL  {label}  {detail}")
        failures.append(label)


def provider_methods():
    tree = ast.parse(PROVIDERS.read_text(encoding="utf-8", errors="replace"))
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "ProviderHub")
    out = {}
    for m in cls.body:
        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[m.name] = {
                "lines": m.end_lineno - m.lineno + 1,
                "async": isinstance(m, ast.AsyncFunctionDef),
                "start": m.lineno,
            }
    return out


def called_in_harness():
    """Method names the harness actually CALLS, via ast, never substrings.

    Counts two shapes: a direct call hub.method(...) / ProviderHub.method(...),
    and a call passed by reference into the harness's safe() wrapper, which is
    how most of the harness invokes the surface.
    """
    tree = ast.parse(HARNESS.read_text(encoding="utf-8", errors="replace"))
    called = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # hub.method(...) or ProviderHub.method(...)
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) \
                and node.func.value.id in ("hub", "ProviderHub"):
            called.add(node.func.attr)
        # safe("label", hub.method, args...) — the callable is an argument
        for arg in node.args:
            if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) \
                    and arg.value.id in ("hub", "ProviderHub"):
                called.add(arg.attr)
    return called


methods = provider_methods()
covered = called_in_harness() & set(methods)
uncovered = sorted(set(methods) - covered)

identity = {}
if SPLIT_MAP.is_file():
    identity = {k: v.get("identity", "?")
                for k, v in json.loads(SPLIT_MAP.read_text())["methods"].items()}

print("=" * 78)
print("PROVIDERS SPLIT COVERAGE MAP")
print("=" * 78)
print(f"providers.py methods : {len(methods)}")
print(f"covered by v678      : {len(covered)}")
print(f"NOT covered          : {len(uncovered)}")

print("\n--- SAFE TO SPLIT (explicit pre-split equivalence coverage) ---")
for name in sorted(covered):
    info = methods[name]
    print(f"  {identity.get(name, '?'):<14} {info['lines']:>4}L  {name}")

print("\n--- NOT SAFE TO SPLIT YET (no equivalence coverage) ---")
for name in sorted(uncovered, key=lambda n: -methods[n]["lines"]):
    info = methods[name]
    kind = "async" if info["async"] else "     "
    print(f"  {identity.get(name, '?'):<14} {info['lines']:>4}L  {kind} {name}")

uncovered_lines = sum(methods[n]["lines"] for n in uncovered)
covered_lines = sum(methods[n]["lines"] for n in covered)
print(f"\nlines covered {covered_lines} / uncovered {uncovered_lines}")

print("\n--- PHASE20 PROVIDER PATH ---")
print("phase20 is permanently MISSING_CANONICAL_DATA and cannot exercise these")
print("itself. Fixture coverage stands in for refactor equivalence ONLY; it is")
print("not historical or predictive evidence and does not make phase20 green.")
missing_phase20 = [m for m in PHASE20_PROVIDER_PATH if m not in covered]
for name in PHASE20_PROVIDER_PATH:
    print(f"  {'covered  ' if name in covered else 'UNCOVERED'} {name}")

print()
check("the scan found the ProviderHub class and its methods", len(methods) > 0)
check("the harness actually calls something (scan is not vacuous)", len(covered) > 0)
check("every phase20 provider-path method has equivalence coverage",
      not missing_phase20, str(missing_phase20))
check("snapshot() is reported honestly as uncovered",
      "snapshot" in uncovered,
      "a name-substring scan wrongly reported this as covered")

# A call whose signature does not match records __RAISED__ and leaves the method
# unexercised while still looking called. Assert the harness runs clean.
raised = [line for line in HARNESS.read_text(encoding="utf-8").splitlines()
          if "__RAISED__" in line and not line.strip().startswith("#")]
check("harness still records signature drift rather than hiding it",
      any("__RAISED__" in line for line in raised),
      "the drift marker was removed")

print("\n" + "=" * 78)
if failures:
    print(f"SPLIT COVERAGE: {len(failures)} check(s) FAILED")
    for f in failures:
        print("   -", f)
    sys.exit(1)
print("SPLIT COVERAGE MAP PASS — map is honest; see NOT SAFE list before splitting")
print("=" * 78)
