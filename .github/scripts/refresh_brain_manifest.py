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

new_files = []
for item in old_files:
    if not isinstance(item, dict) or not item.get("path"):
        raise SystemExit("MANIFEST_FILE_ENTRY_INVALID")
    rel = str(item["path"])
    path = brain_root / rel
    if not path.is_file():
        raise SystemExit(f"MANIFEST_SOURCE_MISSING: {rel}")
    raw = path.read_bytes()
    new_item = dict(item)
    new_item["size"] = len(raw)
    new_item["sha256"] = hashlib.sha256(raw).hexdigest()
    new_files.append(new_item)

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
