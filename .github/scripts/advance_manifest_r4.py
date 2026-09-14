from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "backend" / "clear_nasdaq_brain"
MANIFEST = ROOT / "MANIFEST.json"
EXPECTED_R3_SHA256 = "cedfa8da6e33c474107d65f74ac8bd079ede6d522502fafbe49006feb6703cd9"
EXPECTED_R3_SIZE = 34514
EXPECTED_CHANGED = {
    "tests/test_probability_prompt_contract_v6_4.py",
    "tests/test_release_manifest_v661.py",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def git_head_time() -> str:
    return subprocess.check_output(
        ["git", "show", "-s", "--format=%cI", "HEAD"], cwd=REPO, text=True
    ).strip()


raw = MANIFEST.read_bytes()
obj = json.loads(raw.decode("utf-8"))
rev = obj.get("manifest_revision")

if rev == 4:
    # Idempotent re-run: never rewrite already frozen r4 bytes.
    print("MANIFEST_R4_ALREADY_PRESENT", sha256(MANIFEST), len(raw))
    raise SystemExit(0)

assert rev == 3, rev
assert len(raw) == EXPECTED_R3_SIZE, len(raw)
assert hashlib.sha256(raw).hexdigest() == EXPECTED_R3_SHA256

listed = {x["path"]: x for x in obj["files"]}
mismatches = []
for rel, rec in listed.items():
    p = ROOT / rel
    assert p.is_file(), rel
    actual_size = p.stat().st_size
    actual_sha = sha256(p)
    if rec["size"] != actual_size or rec["sha256"] != actual_sha:
        mismatches.append((rel, rec["size"], rec["sha256"], actual_size, actual_sha))

assert {x[0] for x in mismatches} == EXPECTED_CHANGED, mismatches

# No active Python file may sit outside the manifest.
active_py = {
    p.relative_to(ROOT).as_posix()
    for p in ROOT.rglob("*.py")
    if "__pycache__" not in p.parts
}
assert active_py <= set(listed), sorted(active_py - set(listed))

history = obj["manifest_revision_history"]
assert not [h for h in history if h.get("revision") == 3]
history.append({
    "revision": 3,
    "status": "SUPERSEDED_STALE_TEST_EXPECTATION",
    "manifest_sha256": EXPECTED_R3_SHA256,
    "manifest_size": EXPECTED_R3_SIZE,
    "correction_reason": (
        "After the r1/r2 bookkeeping blocker was repaired, the full baseline suite "
        "reached tests/test_probability_prompt_contract_v6_4.py and exposed a stale "
        "literal-string expectation. Commit 49646b2 had intentionally replaced the "
        "old one-line probability wording with a stronger four-step arithmetic "
        "contract. Revision 4 changes only that stale test expectation plus the "
        "release-manifest test needed to preserve this provenance; fia_brain/prompts.py "
        "and all runtime/model/Forward-OOS logic remain byte-unchanged."
    ),
    "entries_changed_for_revision4": [
        {
            "path": rel,
            "recorded_size": old_size,
            "recorded_sha256": old_sha,
            "actual_size": new_size,
            "actual_sha256": new_sha,
        }
        for rel, old_size, old_sha, new_size, new_sha in sorted(mismatches)
    ],
    "superseded_at_utc": git_head_time(),
    "superseded_by_commit": git_head(),
})

obj["manifest_revision"] = 4
obj["manifest_revision_note"] = (
    "Release version is unchanged. Revision 4 advances integrity metadata only "
    "for a stale probability-prompt TEST expectation exposed after the earlier "
    "manifest blocker was removed. The strengthened runtime prompt from commit "
    "49646b2 is byte-unchanged. No model logic, BASE_FIA, Forward-OOS, sealed "
    "historical artifact, predictive result, or production path is changed."
)

for rec in obj["files"]:
    p = ROOT / rec["path"]
    rec["size"] = p.stat().st_size
    rec["sha256"] = sha256(p)

MANIFEST.write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")
print("MANIFEST_R4_SHA256", sha256(MANIFEST))
print("MANIFEST_R4_SIZE", MANIFEST.stat().st_size)
print("CHANGED_ENTRIES", sorted(EXPECTED_CHANGED))
