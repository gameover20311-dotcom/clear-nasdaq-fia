from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAIN = ROOT / "backend" / "clear_nasdaq_brain"
MANIFEST = BRAIN / "MANIFEST.json"

OLD_MANIFEST_SHA256 = "564b43d0a116021a10f6380fb325b358fd57b50e7abb63fe7b6408dc1842a093"
OLD_MANIFEST_SIZE = 32017

# Exact revision-2 records versus the untouched-main bytes observed by the full
# manifest audit before this repair. The release test's baseline_actual values
# refer to main before the r3 test was authored; its r3 target is separately
# pinned below.
STALE = {
    "fia_brain/cloud_llm.py": {
        "recorded_size": 7738,
        "recorded_sha256": "7fbd5b278a74a6cceff0fbefc3e7eac97ad99fd77f98d01e58e1cab71ab3c31e",
        "baseline_actual_size": 13351,
        "baseline_actual_sha256": "d85828ee3960b5c072e650af18f6d82f8da03e7f6207922c793a513bc7361e69",
        "r3_size": 13351,
        "r3_sha256": "d85828ee3960b5c072e650af18f6d82f8da03e7f6207922c793a513bc7361e69",
    },
    "fia_brain/final_three_brain.py": {
        "recorded_size": 15606,
        "recorded_sha256": "2cf9797876298ac1ac81ea320449a3fdb2c0add072c656d7d8ad791fd4efbf60",
        "baseline_actual_size": 16052,
        "baseline_actual_sha256": "a47ed83b209ceb495d0f3e483fe875e23e9a6e66c2cd1c9cc322428771f65e7f",
        "r3_size": 16052,
        "r3_sha256": "a47ed83b209ceb495d0f3e483fe875e23e9a6e66c2cd1c9cc322428771f65e7f",
    },
    "fia_brain/prompts.py": {
        "recorded_size": 7106,
        "recorded_sha256": "43e03f3a630b6f04033494a857f23e0c3e87204e2bcd89f1444b87f7fd70e3ea",
        "baseline_actual_size": 7501,
        "baseline_actual_sha256": "723f0e68052b1af97e80523a3fd62b597fb4a3e77bf593712883045d4f157c2a",
        "r3_size": 7501,
        "r3_sha256": "723f0e68052b1af97e80523a3fd62b597fb4a3e77bf593712883045d4f157c2a",
    },
    "tests/test_release_manifest_v661.py": {
        "recorded_size": 5411,
        "recorded_sha256": "09a4e47d7bfee6e5e239254fbd6c709697aacf9ef97f0f2eaa08bee61bf427a5",
        "baseline_actual_size": 4574,
        "baseline_actual_sha256": "207c8fa63882a008381c8e375572498be96311237618153930a995177dca0dbe",
        "r3_size": 4999,
        "r3_sha256": "be16866eb112e6c50a6e83a29c504dbe1b1c7aff752ed28ad1e155b184b46bdc",
    },
}

KNOWN_RUNTIME_COMMITS_AFTER_R2 = [
    "369652fcfc2a0d54b4184ac0689058ae498a88ab",
    "a3684086e7192896448aaee89eaa53acad4a177b",
    "bd3c2e9fd2c5a333c2db28a003863cd53e8a6d84",
    "f1e75651db6056eb4a87c990f368e852c6168b7a",
    "49646b2ea5f6e005d54a3c76cad0eedeab565b69",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


assert MANIFEST.stat().st_size == OLD_MANIFEST_SIZE
assert sha256(MANIFEST) == OLD_MANIFEST_SHA256

obj = json.loads(MANIFEST.read_text(encoding="utf-8"))
assert obj["manifest_revision"] == 2
assert not any(h.get("revision") == 2 for h in obj.get("manifest_revision_history", []))
files = {row["path"]: row for row in obj["files"]}

# Prove every old record and every intended r3 target before rewriting metadata.
for rel, rec in STALE.items():
    row = files[rel]
    assert row["size"] == rec["recorded_size"], rel
    assert row["sha256"] == rec["recorded_sha256"], rel
    path = BRAIN / rel
    assert path.is_file(), rel
    assert path.stat().st_size == rec["r3_size"], rel
    assert sha256(path) == rec["r3_sha256"], rel

# Full baseline audit established these are the ONLY mismatches and that no
# active Python file is omitted. Update only those four entries.
for rel, rec in STALE.items():
    files[rel]["size"] = rec["r3_size"]
    files[rel]["sha256"] = rec["r3_sha256"]

obj["manifest_revision"] = 3
obj["manifest_revision_note"] = (
    "Release version is unchanged. Revision 3 advances only integrity metadata "
    "for four exact r2-vs-baseline mismatches found by an exhaustive audit. The "
    "three runtime files are not edited by this repair; the manifest test was "
    "strengthened to enforce r1+r2 provenance and the r3 bytes. No Forward-OOS "
    "seal, protected scientific artifact, historical evidence, or predictive "
    "result is rewritten."
)
obj["manifest_revision_history"].append({
    "revision": 2,
    "status": "SUPERSEDED_STALE_BOOKKEEPING",
    "manifest_sha256": OLD_MANIFEST_SHA256,
    "manifest_size": OLD_MANIFEST_SIZE,
    "entries_misdescribed_at_baseline": [
        {
            "path": rel,
            "recorded_size": rec["recorded_size"],
            "recorded_sha256": rec["recorded_sha256"],
            "baseline_actual_size": rec["baseline_actual_size"],
            "baseline_actual_sha256": rec["baseline_actual_sha256"],
        }
        for rel, rec in STALE.items()
    ],
    "known_runtime_commits_after_r2": KNOWN_RUNTIME_COMMITS_AFTER_R2,
    "correction_reason": (
        "Exhaustive baseline audit found exactly four r2 entries whose recorded "
        "identity did not match the checkout: cloud_llm.py, final_three_brain.py, "
        "prompts.py, and the release-manifest test entry itself. Git history "
        "proves named hosted-GPT-OSS recovery changes for the three runtime files. "
        "The test-entry mismatch is recorded as observed without inventing an "
        "unproven cause. Revision 3 updates bookkeeping only."
    ),
    "superseded_at_utc": "2026-09-14T17:58:54Z",
    "superseded_by": "MANIFEST_REVISION_3_BASELINE_FIA_GATE_REPAIR",
})

MANIFEST.write_text(json.dumps(obj, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")

# Re-audit all listed bytes and all active Python membership after the rewrite.
reloaded = json.loads(MANIFEST.read_text(encoding="utf-8"))
assert reloaded["manifest_revision"] == 3
listed = {row["path"]: row for row in reloaded["files"]}
for rel, row in listed.items():
    path = BRAIN / rel
    assert path.is_file(), rel
    assert path.stat().st_size == row["size"], rel
    assert sha256(path) == row["sha256"], rel
for path in BRAIN.rglob("*.py"):
    if "__pycache__" not in path.parts:
        rel = path.relative_to(BRAIN).as_posix()
        assert rel in listed, rel

print("MANIFEST_REVISION_3_WRITTEN")
print("manifest_size", MANIFEST.stat().st_size)
print("manifest_sha256", sha256(MANIFEST))
