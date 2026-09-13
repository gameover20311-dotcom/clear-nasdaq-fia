#!/usr/bin/env python3
"""A7 — THREE SCIENTIFIC IDENTITIES REGRESSION

Proves the Amendment A s.26 identity split actually separates concerns, using a
disposable mirror of the fingerprint scope so the real tree is never touched.

The split exists because ONE whole-backend fingerprint caused 24 re-seals in six
days with zero forecast locks: adding fia/auth_api.py invalidated a campaign
whose model had not changed by a single coefficient.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from fia import identity as ident  # noqa: E402

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + (("  -> " + str(detail)[:170]) if not ok else ""))


def digests(root: Path):
    return {i: ident.fingerprint(i, root)["digest"] for i in ident.IDENTITIES}


# ---------------------------------------------------------------- registry
cls = ident.classification_map()
scope = ident.scope_files(BACKEND)
check("A7-1 every file in fingerprint scope is classified",
      ident.unclassified_files(BACKEND) == [], str(ident.unclassified_files(BACKEND)))
check("A7-2 each file has exactly one identity",
      all(cls[r] in ident.IDENTITIES for r in scope))
check("A7-3 all three identities are non-empty",
      all(sum(1 for r in scope if cls[r] == i) > 0 for i in ident.IDENTITIES),
      str({i: sum(1 for r in scope if cls[r] == i) for i in ident.IDENTITIES}))
check("A7-4 identities partition the scope with no overlap",
      sum(sum(1 for r in scope if cls[r] == i) for i in ident.IDENTITIES) == len(scope))

# ---------------------------------------------------------------- mirror
tmp = Path(tempfile.mkdtemp(prefix="fia_identity_"))
mirror = tmp / "backend"
for rel in scope:
    dst = mirror / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BACKEND / rel, dst)

base = digests(mirror)
check("A7-5 mirror reproduces a full classified scope",
      ident.unclassified_files(mirror) == [], str(ident.unclassified_files(mirror)))
check("A7-6 identical trees reproduce identical fingerprints (determinism)",
      digests(mirror) == base, "second pass differed")

real = digests(BACKEND)
check("A7-7 mirror of the real tree equals the real tree's fingerprints",
      real == base, f"{real} vs {base}")

# ---------------------------------------------------------------- isolation
SAMPLES = {
    "INFRASTRUCTURE": "fia/forward_oos_durable.py",   # durable mirroring plumbing
    "MODEL": "fia/premove_engine.py",                 # abstention decision logic
    "PROTOCOL": "fia/provider_reliability.py",        # staleness / source eligibility
}
for expected_identity, rel in SAMPLES.items():
    assert cls[rel] == expected_identity, f"{rel} is classified {cls[rel]}"
    target = mirror / rel
    original = target.read_bytes()
    target.write_bytes(original + b"\n# identity-isolation probe\n")
    now = digests(mirror)
    changed = sorted(i for i in ident.IDENTITIES if now[i] != base[i])
    unchanged = sorted(i for i in ident.IDENTITIES if now[i] == base[i])
    check(f"A7-8 [{expected_identity}] editing {rel} changes ONLY {expected_identity}",
          changed == [expected_identity], f"changed={changed} unchanged={unchanged}")
    target.write_bytes(original)
    check(f"A7-9 [{expected_identity}] restoring the file restores all digests",
          digests(mirror) == base)

# ---------------------------------------------------------------- fail-closed
stray = mirror / "fia" / "unclassified_new_module.py"
stray.write_text("# a new module nobody classified\n", encoding="utf-8")
check("A7-10 an unclassified new module is detected",
      ident.unclassified_files(mirror) == ["fia/unclassified_new_module.py"],
      str(ident.unclassified_files(mirror)))
raised = False
try:
    ident.fingerprint("MODEL", mirror)
except RuntimeError as exc:
    raised = "IDENTITY_CLASSIFICATION_INCOMPLETE" in str(exc)
check("A7-11 fingerprinting FAILS CLOSED while a file is unclassified", raised)
stray.unlink()
check("A7-12 removing it restores fingerprints exactly", digests(mirror) == base)

# ---------------------------------------------------------------- honesty
hist = ident.historical_identity_available({"campaign_id": "CLEAR-NASDAQ-FORWARD-OOS-V6-V672",
                                            "model_fingerprint": {"digest": "5c2b7279"}})
check("A7-13 a pre-split campaign reports UNAVAILABLE, not a reconstructed digest",
      hist["status"] == "UNAVAILABLE_SEALED_BEFORE_IDENTITY_SPLIT" and hist["reconstructed"] is False,
      str(hist))

allfp = ident.all_fingerprints(BACKEND)
check("A7-14 all three identities are individually reportable",
      all(allfp[i.lower()]["digest"] for i in ident.IDENTITIES))

# ---------------------------------------------------------------- A7.2 manifest
doc = ident._classification()
check("A7.2-1 classification manifest id is deterministic",
      ident.compute_classification_manifest_id(doc["schema"], doc["classification"])
      == ident.compute_classification_manifest_id(
          doc["schema"], dict(reversed(list(doc["classification"].items())))))
check("A7.2-2 live manifest matches the code-pinned id",
      ident.classification_manifest_id() == ident.EXPECTED_CLASSIFICATION_MANIFEST_ID)
check("A7.2-3 fingerprint report states WHICH manifest produced the digests",
      allfp["classification_manifest_id"] == ident.EXPECTED_CLASSIFICATION_MANIFEST_ID)

repartitioned = dict(doc["classification"])
first_model = sorted(k for k, v in repartitioned.items() if v == "MODEL")[0]
repartitioned[first_model] = "INFRASTRUCTURE"
check("A7.2-4 re-partitioning the SAME files changes the manifest id",
      ident.compute_classification_manifest_id(doc["schema"], repartitioned)
      != ident.EXPECTED_CLASSIFICATION_MANIFEST_ID)

check("A7.2-5 every resolved module carries call-path evidence",
      all(("call_path" in v or v.get("method") == "user-approved") and "verdict" in v
          for v in ident.resolved_classifications().values()),
      str(sorted(ident.resolved_classifications())))
blocked = ident.blocked_pending_split()
check("A7.2-6 unverifiable splits are recorded as BLOCKED, not silently assigned",
      blocked.get("status") == "BLOCKED_INSUFFICIENT_VERIFICATION_COVERAGE"
      and blocked.get("coverage", {}).get("env_blocked", 0) > 0,
      str(blocked.get("status")))
check("A7-15 legacy whole-backend digest is retained and labelled, not replaced",
      bool(allfp["legacy_deployment_fingerprint"]["digest"]))

shutil.rmtree(tmp, ignore_errors=True)

failed = [n for n, ok, _ in CHECKS if not ok]
print()
print("=" * 46)
if failed:
    print("A7 IDENTITY SPLIT: FAIL")
    print("failed =", failed)
    raise SystemExit(1)
print(f"A7 IDENTITY SPLIT: PASS  ({len(CHECKS)}/{len(CHECKS)})")
for i in ident.IDENTITIES:
    fp = allfp[i.lower()]
    print(f"{i:<15} {fp['digest'][:32]}  files={fp['file_count']}")
print(f"{'LEGACY(deploy)':<15} {allfp['legacy_deployment_fingerprint']['digest'][:32]}"
      f"  files={allfp['legacy_deployment_fingerprint']['file_count']}")
print("review_required =", allfp["review_required"])
print("=" * 46)
