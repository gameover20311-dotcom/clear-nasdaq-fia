from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAIN = ROOT / "backend" / "clear_nasdaq_brain"
TARGETS = [
    BRAIN / "fia_brain" / "cloud_llm.py",
    BRAIN / "tests" / "test_release_manifest_v661.py",
    BRAIN / "MANIFEST.json",
]

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

for p in TARGETS:
    print(json.dumps({
        "path": p.relative_to(ROOT).as_posix(),
        "size": p.stat().st_size,
        "sha256": sha256(p),
    }, sort_keys=True))
