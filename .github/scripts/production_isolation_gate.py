#!/usr/bin/env python3
"""Fail-closed static boundary gate for CLEAR NASDAQ production surfaces.

This is not a complete security proof. It is a hostile static guard for the
specific scientific boundary: known research/shadow packages must not acquire
an undeclared production import path. The scanner covers direct imports,
aliased importlib usage, from-import aliases, simple statically-resolvable
string construction, config variables, and forbidden module literals. Its own
hostile self-test runs before the real repository scan in CI.
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
        if path.name.startswith("test_") or "/tests/" in path.as_posix():
            continue
        if "__pycache__" in path.parts:
            continue
        yield path


def _static_string(node: ast.AST, bindings: dict[str, str]) -> str | None:
    """Resolve a deliberately small, safe subset of static string expressions."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string(node.left, bindings)
        right = _static_string(node.right, bindings)
        if left is not None and right is not None:
            return left + right
        return None
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                piece = _static_string(value.value, bindings)
                if piece is None:
                    return None
                parts.append(piece)
            else:
                return None
        return "".join(parts)
    return None


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

    importlib_aliases = {"importlib"}
    import_module_aliases: set[str] = set()
    bindings: dict[str, str] = {}

    def add(kind: str, node: ast.AST, detail: str) -> None:
        item = {
            "path": label,
            "kind": kind,
            "line": getattr(node, "lineno", 0),
            "detail": detail,
        }
        if item not in violations:
            violations.append(item)

    # Pass 1: learn obvious aliases and statically resolvable string bindings.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_aliases.add(alias.asname or "importlib")
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    import_module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            value_node = node.value
            if value_node is None:
                continue
            value = _static_string(value_node, bindings)
            if value is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = value

    # Pass 2: detect production-boundary references.
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
            dynamic_import = False
            func_label = ""
            if isinstance(node.func, ast.Name):
                if node.func.id == "__import__" or node.func.id in import_module_aliases:
                    dynamic_import = True
                    func_label = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                if node.func.value.id in importlib_aliases and node.func.attr == "import_module":
                    dynamic_import = True
                    func_label = f"{node.func.value.id}.import_module"

            if dynamic_import and node.args:
                module_name = _static_string(node.args[0], bindings)
                if module_name is not None and _is_forbidden(module_name):
                    add("DYNAMIC_IMPORT", node, f"{func_label}({module_name!r})")

        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _is_forbidden(node.value):
                add("FORBIDDEN_LITERAL", node, node.value[:240])

        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            value_node = node.value
            if value_node is not None:
                value = _static_string(value_node, bindings)
                if value is not None and _is_forbidden(value):
                    add("FORBIDDEN_STATIC_BINDING", node, value[:240])

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
        "importlib_alias": ("import importlib as il\nx=il.import_module('dpcse_v23_shadow')\n", 1),
        "from_importlib_alias": ("from importlib import import_module as load\nx=load('mfre_v125_shadow')\n", 1),
        "concatenated_dynamic": ("import importlib\nx=importlib.import_module('dpcse_' + 'v23_shadow')\n", 1),
        "bound_dynamic": ("import importlib\nMODULE='mfre_' + 'v125_shadow'\nx=importlib.import_module(MODULE)\n", 1),
        "constant_fstring_dynamic": ("import importlib\nPART='cnmi_shadow'\nx=importlib.import_module(f'research.{PART}')\n", 1),
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
