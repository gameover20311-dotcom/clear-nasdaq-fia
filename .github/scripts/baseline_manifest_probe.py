from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAIN = ROOT / "backend" / "clear_nasdaq_brain"
MANIFEST = BRAIN / "MANIFEST.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

obj = json.loads(MANIFEST.read_text(encoding="utf-8"))
listed = {row["path"]: row for row in obj["files"]}

print("MANIFEST_REVISION", obj.get("manifest_revision"))
print("MANIFEST_SIZE", MANIFEST.stat().st_size)
print("MANIFEST_SHA256", sha256(MANIFEST))

mismatches = []
missing = []
for rel, row in sorted(listed.items()):
    path = BRAIN / rel
    if not path.is_file():
        missing.append(rel)
        continue
    actual_size = path.stat().st_size
    actual_sha = sha256(path)
    if actual_size != row["size"] or actual_sha != row["sha256"]:
        rec = {
            "path": rel,
            "recorded_size": row["size"],
            "actual_size": actual_size,
            "recorded_sha256": row["sha256"],
            "actual_sha256": actual_sha,
        }
        mismatches.append(rec)
        print("MISMATCH", json.dumps(rec, sort_keys=True))

active_python = sorted(
    p.relative_to(BRAIN).as_posix()
    for p in BRAIN.rglob("*.py")
    if "__pycache__" not in p.parts
)
omitted = [rel for rel in active_python if rel not in listed]

print("MISMATCH_COUNT", len(mismatches))
print("MISSING_LISTED_COUNT", len(missing))
for rel in missing:
    print("MISSING_LISTED", rel)
print("OMITTED_ACTIVE_PYTHON_COUNT", len(omitted))
for rel in omitted:
    print("OMITTED_ACTIVE_PYTHON", rel)
