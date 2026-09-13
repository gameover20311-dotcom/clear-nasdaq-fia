#!/usr/bin/env python3
"""A6.1 — ARTIFACT GUARD FAIL-CLOSED REGRESSION

Three gaps found on review of the A6 implementation:

  Gap 1  _registry() fell back to {} when protected_artifacts.json was missing,
         unreadable or malformed. A damaged registry therefore silently
         disabled ALL artifact protection — the precise failure this module
         exists to prevent.

  Gap 2  guarded_output_path() consulted the registry before the sealed
         prefixes, so a brand-new file nobody had registered yet could be
         written canonically INSIDE the evidence base.

  Gap 3  Nothing protected the registry itself. Replacing it with a
         self-consistent forgery would have blessed mutated bytes.

The real registry file is never written by this suite; scenarios point the
module at temporary copies and restore the original path afterwards.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from fia import artifact_guard as ag  # noqa: E402

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + (("  -> " + str(detail)[:170]) if not ok else ""))


REAL_PATH = ag.REGISTRY_PATH
REAL_DOC = json.loads(REAL_PATH.read_text(encoding="utf-8"))
TMP = Path(tempfile.mkdtemp(prefix="fia_guard_failclosed_"))


def with_registry(doc_or_none, *, raw: str = None):
    """Point the guard at a temporary registry and return the raised error."""
    ag._REGISTRY = None
    if doc_or_none is None and raw is None:
        ag.REGISTRY_PATH = TMP / "does_not_exist.json"
    else:
        p = TMP / "registry.json"
        p.write_text(raw if raw is not None else json.dumps(doc_or_none), encoding="utf-8")
        ag.REGISTRY_PATH = p
    try:
        ag._registry()
        return None
    except ag.RegistryIntegrityError as exc:
        return str(exc)
    finally:
        ag.REGISTRY_PATH = REAL_PATH
        ag._REGISTRY = None


# ------------------------------------------------------------ Gap 1
err = with_registry(None)
check("A6.1-1 MISSING registry raises instead of failing open",
      err is not None and "REGISTRY_MISSING" in err, str(err))

err = with_registry(None, raw="{ this is not json ")
check("A6.1-2 MALFORMED JSON raises",
      err is not None and "MALFORMED_JSON" in err, str(err))

err = with_registry({"schema": "SOMETHING_ELSE", "artifacts": {"a": "0" * 64}})
check("A6.1-3 WRONG SCHEMA raises",
      err is not None and "INVALID_SCHEMA" in err, str(err))

err = with_registry({"schema": ag.REGISTRY_SCHEMA, "artifacts": {}})
check("A6.1-4 EMPTY artifacts map raises",
      err is not None and "INVALID_SCHEMA" in err, str(err))

err = with_registry({"schema": ag.REGISTRY_SCHEMA, "artifacts": {"x.csv": "short"}})
check("A6.1-5 malformed digest entry raises",
      err is not None and "INVALID_SCHEMA" in err, str(err))

check("A6.1-6 an empty registry is never substituted",
      ag._registry() == dict(REAL_DOC["artifacts"]) and len(ag._registry()) > 100,
      str(len(ag._registry())))

# ------------------------------------------------------------ Gap 3
tampered = json.loads(json.dumps(REAL_DOC))
first = sorted(tampered["artifacts"])[0]
tampered["artifacts"][first] = "f" * 64           # bless a mutated artifact
err = with_registry(tampered)
check("A6.1-7 tampered entry breaks the manifest id and raises",
      err is not None and "MANIFEST_MISMATCH" in err, str(err))

forged = json.loads(json.dumps(REAL_DOC))
forged["artifacts"][first] = "e" * 64
forged["manifest_id"] = ag.compute_manifest_id(forged["schema"], forged["artifacts"])
err = with_registry(forged)
check("A6.1-8 SELF-CONSISTENT forgery still fails against the code-pinned id",
      err is not None and "NOT_THE_PINNED_MANIFEST" in err, str(err))

check("A6.1-9 manifest id is deterministic",
      ag.compute_manifest_id(REAL_DOC["schema"], REAL_DOC["artifacts"])
      == ag.compute_manifest_id(REAL_DOC["schema"], dict(reversed(list(REAL_DOC["artifacts"].items())))))
check("A6.1-10 live registry matches the pinned manifest id",
      ag.registry_manifest_id() == ag.EXPECTED_MANIFEST_ID, ag.registry_manifest_id())

src = Path(ag.__file__).read_text(encoding="utf-8")
check("A6.1-11 the guard never re-records expected hashes on mismatch",
      ("EXPECTED_MANIFEST_ID =" in src) and ("artifacts\"] =" not in src) and ("write_text" not in src),
      "guard module must contain no registry-writing code")

# ------------------------------------------------------------ Gap 2
for prefix in ag.SEALED_PREFIXES:
    brand_new = BACKEND / prefix / "brand_new_unregistered_probe.json"
    check(f"A6.1-12 unregistered file under {prefix} is NOT registered",
          not ag.is_protected(brand_new))
    check(f"A6.1-13 unregistered file under {prefix} is still SEALED",
          ag.is_sealed(brand_new))
    check(f"A6.1-14 unregistered file under {prefix} cannot be written canonically",
          ag.guarded_output_path(brand_new) != brand_new,
          str(ag.guarded_output_path(brand_new)))

import os  # noqa: E402
os.environ[ag.REGEN_ENV_VAR] = "1"
import importlib  # noqa: E402
importlib.reload(ag)
for prefix in ag.SEALED_PREFIXES:
    brand_new = BACKEND / prefix / "brand_new_unregistered_probe.json"
    check(f"A6.1-15 regen flag does NOT unlock unregistered sealed path {prefix}",
          ag.guarded_output_path(brand_new) != brand_new)
os.environ.pop(ag.REGEN_ENV_VAR, None)
importlib.reload(ag)

outside = BACKEND / "some_unrelated_scratch_dir" / "x.json"
check("A6.1-16 an ordinary unregistered path outside sealed prefixes still passes through",
      ag.guarded_output_path(outside) == outside)

import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)

failed = [n for n, ok, _ in CHECKS if not ok]
print()
print("=" * 48)
if failed:
    print("A6.1 FAIL-CLOSED GUARD: FAIL")
    print("failed =", failed)
    raise SystemExit(1)
print(f"A6.1 FAIL-CLOSED GUARD: PASS  ({len(CHECKS)}/{len(CHECKS)})")
print("registry_fails_open        = NO")
print("sealed_prefix_bypass       = NO")
print("registry_self_protected    = YES (manifest id pinned in code)")
print("expected_hashes_auto_rewritten = NO")
print("=" * 48)
