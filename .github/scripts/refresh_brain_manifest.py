import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
backend = repo / "backend"
manifest_path = backend / "clear_nasdaq_brain" / "MANIFEST.json"
data = json.loads(manifest_path.read_text(encoding="utf-8"))
old_files = data.get("files") or {}
new_files = {}

for rel in old_files:
    path = backend / rel
    if not path.is_file():
        raise SystemExit(f"MANIFEST_SOURCE_MISSING: {rel}")
    raw = path.read_bytes()
    new_files[rel] = {
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }

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
