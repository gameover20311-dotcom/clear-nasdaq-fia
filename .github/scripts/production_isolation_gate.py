#!/usr/bin/env python3
"""Fail-closed static boundary gate for CLEAR NASDAQ production surfaces.

This is deliberately narrower than a security proof: it checks the declared
production Python surfaces for direct, indirect-literal, and dynamic-import
references to research/shadow packages. It also runs hostile self-tests so a
broken scanner cannot silently report PASS.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ROOTS = (
    ROOT / "backend" / "main.py",
    ROOT / "backend" / "fia",
    ROOT / "backend" / "fia_final_cockpit",
)

FORBIDDEN_TOKENS = (
    "research.cnmi_shadow",
    "cnmi_shadow",
    "umse_master",
    "umse_master_v2",
    "simons_shadow_lab_v1",
    "dpcse_v23_shadow",
    "nq_mbo_adapter",
    "mfre_v125_shadow",
)


def _is_forbidden(text: str) -> bool:
    return any(token in text for token in FORBIDDEN_TOKENS)


def _iter_python_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        if root.suffix == ".py":
            yield root
        return
    if not root.exists():
        return
    for path in sorted(root.rglob("*.py")):
        # Test modules are not runtime production surfaces.
        if path.name.startswith("test_") or "/tests/" in path.as_posix():
            continue
        if "__pycache__" in path.parts:
            continue
        yield path


def scan_source(source: str, label: str = "<memory>") -> list[dict[str, object]]:
    violations: list[dict[str, object]] = []
    try:
        tree = ast.parse(source, filename=label)
    except SyntaxError as exc:
        return [{
            "path": label,
            "kind": "SYNTAX_ERROR",
            "line": exc.lineno or 0,
            "detail": str(exc),
        }]

    def add(kind: str, node: ast.AST, detail: str) -> None:
        violations.append({
            "path": label,
            "kind": kind,
            "line": getattr(node, "lineno", 0),
            "detail": detail,
        })

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    add("IMPORT", node, alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _is_forbidden(module):
                add("IMPORT_FROM", node, module)
        elif isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                func_name = f"{node.func.value.id}.{node.func.attr}"
            if func_name in {"__import__", "importlib.import_module"} and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and _is_forbidden(arg.value):
                    add("DYNAMIC_IMPORT", node, f"{func_name}({arg.value!r})")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Catches config-driven module paths or wrappers that avoid a direct import.
            if _is_forbidden(node.value):
                add("FORBIDDEN_LITERAL", node, node.value[:240])

    return violations


def scan_repository() -> list[dict[str, object]]:
    violations: list[dict[str, object]] = []
    seen: set[Path] = set()
    for root in PRODUCTION_ROOTS:
        for path in _iter_python_files(root):
            if path in seen:
                continue
            seen.add(path)
            rel = path.relative_to(ROOT).as_posix()
            violations.extend(scan_source(path.read_text(encoding="utf-8", errors="strict"), rel))
    return violations


def hostile_self_test() -> dict[str, object]:
    cases = {
        "clean": ("import json\nVALUE='safe'\n", 0),
        "direct_import": ("import dpcse_v23_shadow\n", 1),
        "from_import": ("from mfre_v125_shadow import status\n", 1),
        "builtin_dynamic": ("x=__import__('research.cnmi_shadow')\n", 1),
        "importlib_dynamic": ("import importlib\nx=importlib.import_module('nq_mbo_adapter.rithmic')\n", 1),
        "config_literal": ("MODULE='simons_shadow_lab_v1.runner'\n", 1),
    }
    results: dict[str, object] = {}
    ok = True
    for name, (src, minimum) in cases.items():
        found = scan_source(src, f"<selftest:{name}>")
        passed = len(found) >= minimum if minimum else len(found) == 0
        results[name] = {"violations": len(found), "pass": passed}
        ok = ok and passed
    return {"pass": ok, "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        report = hostile_self_test()
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["pass"] else 2

    violations = scan_repository()
    report = {
        "production_roots": [p.relative_to(ROOT).as_posix() for p in PRODUCTION_ROOTS],
        "forbidden_tokens": list(FORBIDDEN_TOKENS),
        "violations": violations,
        "status": "PASS" if not violations else "FAIL",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
