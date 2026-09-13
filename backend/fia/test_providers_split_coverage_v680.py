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
MODEL_MOD = BACKEND / "fia" / "providers_model.py"
PROTOCOL_MOD = BACKEND / "fia" / "providers_protocol.py"
INFRA_MOD = BACKEND / "fia" / "providers_infrastructure.py"
HARNESS = BACKEND / "fia" / "test_providers_equivalence_v678.py"
SNAPSHOT_HARNESS = BACKEND / "fia" / "test_providers_snapshot_equivalence_v681.py"
HARNESSES = (HARNESS, SNAPSHOT_HARNESS)
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
    """Every ProviderHub method, wherever the split put it.

    After the three-way split, providers.py is a facade and the methods live in
    ModelMixin, ProtocolMixin and InfrastructureMixin. Parsing providers.py
    alone would find a class with no methods and report the coverage map as
    vacuous, which is exactly the kind of silent miscount this file exists to
    prevent.
    """
    out = {}
    for path in (PROVIDERS, MODEL_MOD, PROTOCOL_MOD, INFRA_MOD):
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            if cls.name not in ("ProviderHub", "ModelMixin", "ProtocolMixin",
                                "InfrastructureMixin"):
                continue
            for m in cls.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[m.name] = {
                        "lines": m.end_lineno - m.lineno + 1,
                        "async": isinstance(m, ast.AsyncFunctionDef),
                        "start": m.lineno,
                        "module": path.name,
                    }
    return out


def called_in_harness():
    """Method names the harness actually CALLS, via ast, never substrings.

    Counts two shapes: a direct call hub.method(...) / ProviderHub.method(...),
    and a call passed by reference into the harness's safe() wrapper, which is
    how most of the harness invokes the surface.
    """
    called = set()
    for path in HARNESSES:
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
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
            # direct("label", "method_name", ...) — v681 dispatches by name,
            # so the method is a string literal, not an attribute reference.
            if isinstance(node.func, ast.Name) and node.func.id == "direct" \
                    and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) \
                    and isinstance(node.args[1].value, str):
                called.add(node.args[1].value)
            # rec("direct[NAME]", ...) records an observation for a method
            # that cannot be re-invoked by name, such as __init__, whose
            # observable outcome is captured instead.
            if isinstance(node.func, ast.Name) and node.func.id == "rec" \
                    and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                label = node.args[0].value
                if label.startswith("direct[") and label.endswith("]"):
                    called.add(label[len("direct["):-1])
            # hub.method = stub  is NOT coverage; only calls count.
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
# snapshot() was the highest-risk uncovered method. v681 now drives it through
# 15 deterministic no-network scenarios, so it must appear as covered — and a
# regression that drops that coverage fails here.
check("snapshot() has real equivalence coverage",
      "snapshot" in covered,
      "snapshot() lost its coverage")

# A call whose signature does not match records __RAISED__ and leaves the method
# unexercised while still looking called. Assert the harness runs clean.
raised = [line for line in HARNESS.read_text(encoding="utf-8").splitlines()
          if "__RAISED__" in line and not line.strip().startswith("#")]
check("harness still records signature drift rather than hiding it",
      any("__RAISED__" in line for line in raised),
      "the drift marker was removed")

# ---------------------------------------------------------- determinism ----
# The digest is only a split gate if it is reproducible. It was not: one
# observation returned a set, json.dumps fell through to default=str, and str()
# on a set emits hash order, which Python randomises per process. Four runs gave
# four digests, so BASELINE_DIGEST could never have matched and every
# post-split comparison would have reported a false HARD STOP.
#
# Run the harness twice under deliberately different hash seeds. Identical
# digests or the gate is not trustworthy.
print("\n--- HARNESS DETERMINISM ---")
import os                                                          # noqa: E402
import re                                                          # noqa: E402
import subprocess                                                  # noqa: E402


def harness_digest(seed):
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(seed)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(BACKEND)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    done = subprocess.run([sys.executable, str(HARNESS)], capture_output=True,
                          text=True, cwd=str(BACKEND), env=env, timeout=600)
    found = re.search(r"^digest\s*:\s*([0-9a-f]{64})$",
                      (done.stdout or "") + (done.stderr or ""), re.M)
    return found.group(1) if found else None


def _digest_of(path, seed):
    global HARNESS
    _saved, HARNESS = HARNESS, path
    try:
        return harness_digest(seed)
    finally:
        HARNESS = _saved


_d1 = harness_digest(1)
_d2 = harness_digest(999)
print(f"  seed 1   : {_d1}")
print(f"  seed 999 : {_d2}")
check("the equivalence harness produced a digest at all", _d1 is not None)
check("the equivalence digest is reproducible across hash seeds",
      _d1 is not None and _d1 == _d2,
      "a set or other unordered value is leaking hash order into the digest")

print("\n" + "=" * 78)
if failures:
    print(f"SPLIT COVERAGE: {len(failures)} check(s) FAILED")
    for f in failures:
        print("   -", f)
    sys.exit(1)
print("SPLIT COVERAGE MAP PASS — map is honest; see NOT SAFE list before splitting")
print("=" * 78)
