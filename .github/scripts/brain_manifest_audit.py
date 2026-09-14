#!/usr/bin/env python3
"""Independent audit of the shipped CLEAR NASDAQ brain release manifest.

The audit lives outside backend/clear_nasdaq_brain so it cannot change the
payload it is measuring. It reports every manifest mismatch with actual size and
SHA-256, and fails closed on unlisted Python files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAIN = ROOT / "backend" / "clear_nasdaq_brain"
MANIFEST = BRAIN / "MANIFEST.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    obj = json.loads(MANIFEST.read_text(encoding="utf-8"))
    listed = {x["path"]: x for x in obj.get("files", [])}
    mismatches = []
    missing = []

    for rel, expected in sorted(listed.items()):
        p = BRAIN / rel
        if not p.is_file():
            missing.append(rel)
            continue
        actual = {"size": p.stat().st_size, "sha256": sha256(p)}
        if actual["size"] != expected.get("size") or actual["sha256"] != expected.get("sha256"):
            mismatches.append({
                "path": rel,
                "expected_size": expected.get("size"),
                "actual_size": actual["size"],
                "expected_sha256": expected.get("sha256"),
                "actual_sha256": actual["sha256"],
            })

    unlisted_python = []
    for p in sorted(BRAIN.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(BRAIN).as_posix()
        if rel not in listed:
            unlisted_python.append(rel)

    report = {
        "manifest_revision": obj.get("manifest_revision"),
        "manifest_bytes": MANIFEST.stat().st_size,
        "manifest_sha256": sha256(MANIFEST),
        "listed_files": len(listed),
        "missing": missing,
        "mismatches": mismatches,
        "unlisted_python": unlisted_python,
    }
    report["status"] = "PASS" if not (missing or mismatches or unlisted_python) else "FAIL"
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
