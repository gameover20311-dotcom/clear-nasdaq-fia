import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
brain_root = repo / "backend" / "clear_nasdaq_brain"
manifest_path = brain_root / "MANIFEST.json"
data = json.loads(manifest_path.read_text(encoding="utf-8"))
old_files = data.get("files") or []
if not isinstance(old_files, list):
    raise SystemExit("MANIFEST_FILES_SCHEMA_INVALID")

# Preserve the release's existing non-Python inventory, but refresh every
# existing entry from current bytes and add any active Python source/test that
# was omitted. The release test explicitly requires complete Python coverage.
ordered_paths = []
seen = set()
for item in old_files:
    if not isinstance(item, dict) or not item.get("path"):
        raise SystemExit("MANIFEST_FILE_ENTRY_INVALID")
    rel = str(item["path"])
    if rel not in seen:
        ordered_paths.append(rel)
        seen.add(rel)

for path in sorted(brain_root.rglob("*.py")):
    if "__pycache__" in path.parts:
        continue
    rel = path.relative_to(brain_root).as_posix()
    if rel not in seen:
        ordered_paths.append(rel)
        seen.add(rel)

new_files = []
for rel in ordered_paths:
    path = brain_root / rel
    if not path.is_file():
        raise SystemExit(f"MANIFEST_SOURCE_MISSING: {rel}")
    raw = path.read_bytes()
    new_files.append({
        "path": rel,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    })

if new_files != old_files:
    data["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["files"] = new_files
    manifest_path.write_text(
        json.dumps(data, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print("brain manifest refreshed")
else:
    print("brain manifest already current")
