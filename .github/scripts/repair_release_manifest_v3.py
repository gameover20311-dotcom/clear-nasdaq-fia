from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAIN = ROOT / "backend" / "clear_nasdaq_brain"
MANIFEST = BRAIN / "MANIFEST.json"
CLOUD = BRAIN / "fia_brain" / "cloud_llm.py"
RELEASE_TEST = BRAIN / "tests" / "test_release_manifest_v661.py"

OLD_MANIFEST_SHA256 = "564b43d0a116021a10f6380fb325b358fd57b50e7abb63fe7b6408dc1842a093"
OLD_MANIFEST_SIZE = 32017
OLD_CLOUD_SHA256 = "7fbd5b278a74a6cceff0fbefc3e7eac97ad99fd77f98d01e58e1cab71ab3c31e"
OLD_CLOUD_SIZE = 7738
NEW_CLOUD_SHA256 = "d85828ee3960b5c072e650af18f6d82f8da03e7f6207922c793a513bc7361e69"
NEW_CLOUD_SIZE = 13351
EXPECTED_TEST_SHA256 = "94ef5b922932048848a494bc245d67b025c839e65dc48361059230ae39ed5398"
EXPECTED_TEST_SIZE = 5441


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


assert MANIFEST.stat().st_size == OLD_MANIFEST_SIZE
assert sha256(MANIFEST) == OLD_MANIFEST_SHA256
assert CLOUD.stat().st_size == NEW_CLOUD_SIZE
assert sha256(CLOUD) == NEW_CLOUD_SHA256
assert RELEASE_TEST.stat().st_size == EXPECTED_TEST_SIZE
assert sha256(RELEASE_TEST) == EXPECTED_TEST_SHA256

obj = json.loads(MANIFEST.read_text(encoding="utf-8"))
assert obj["manifest_revision"] == 2
assert not any(h.get("revision") == 2 for h in obj.get("manifest_revision_history", []))

files = {row["path"]: row for row in obj["files"]}
cloud = files["fia_brain/cloud_llm.py"]
assert cloud["size"] == OLD_CLOUD_SIZE
assert cloud["sha256"] == OLD_CLOUD_SHA256
cloud["size"] = NEW_CLOUD_SIZE
cloud["sha256"] = NEW_CLOUD_SHA256

test = files["tests/test_release_manifest_v661.py"]
test["size"] = EXPECTED_TEST_SIZE
test["sha256"] = EXPECTED_TEST_SHA256

obj["manifest_revision"] = 3
obj["manifest_revision_note"] = (
    "Release version is unchanged. Revision 3 advances only the integrity record "
    "after authorized hosted-GPT-OSS runtime-recovery commits changed cloud_llm.py "
    "without refreshing MANIFEST.json. Revisions 1 and 2 remain append-only below; "
    "no Forward-OOS seal, protected scientific artifact, historical evidence, or "
    "predictive result is rewritten by this bookkeeping repair."
)
obj["manifest_revision_history"].append({
    "revision": 2,
    "status": "SUPERSEDED_STALE_BOOKKEEPING",
    "manifest_sha256": OLD_MANIFEST_SHA256,
    "manifest_size": OLD_MANIFEST_SIZE,
    "stale_entry": {
        "path": "fia_brain/cloud_llm.py",
        "recorded_size": OLD_CLOUD_SIZE,
        "actual_size": NEW_CLOUD_SIZE,
        "recorded_sha256": OLD_CLOUD_SHA256,
        "actual_sha256": NEW_CLOUD_SHA256,
    },
    "later_runtime_recovery_commits": [
        "369652fcfc2a0d54b4184ac0689058ae498a88ab",
        "a3684086e7192896448aaee89eaa53acad4a177b",
        "bd3c2e9fd2c5a333c2db28a003863cd53e8a6d84",
    ],
    "correction_reason": (
        "Revision 2 correctly repaired the original Groq-adapter manifest defect, "
        "but later authorized provider-runtime resilience commits changed only the "
        "hosted adapter implementation and did not refresh MANIFEST.json. The stale "
        "record therefore no longer matched shipped bytes. Revision 3 records those "
        "actual bytes without altering cloud_llm.py or scientific/Forward-OOS logic."
    ),
    "superseded_at_utc": "2026-09-14T17:50:41Z",
    "superseded_by": "MANIFEST_REVISION_3_BASELINE_FIA_GATE_REPAIR",
})

MANIFEST.write_text(json.dumps(obj, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")

# Post-write structural verification. MANIFEST does not hash itself.
reloaded = json.loads(MANIFEST.read_text(encoding="utf-8"))
assert reloaded["manifest_revision"] == 3
listed = {row["path"]: row for row in reloaded["files"]}
assert listed["fia_brain/cloud_llm.py"]["sha256"] == NEW_CLOUD_SHA256
assert listed["fia_brain/cloud_llm.py"]["size"] == NEW_CLOUD_SIZE
assert listed["tests/test_release_manifest_v661.py"]["sha256"] == EXPECTED_TEST_SHA256
assert listed["tests/test_release_manifest_v661.py"]["size"] == EXPECTED_TEST_SIZE
print("MANIFEST_REVISION_3_WRITTEN")
print("manifest_size", MANIFEST.stat().st_size)
print("manifest_sha256", sha256(MANIFEST))
