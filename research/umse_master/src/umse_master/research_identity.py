from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Mapping


IDENTITIES = ("MODEL", "PROTOCOL", "INFRASTRUCTURE")
SOURCE_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = SOURCE_ROOT.parents[1] / "spec" / "umse_identity_classification_v1.json"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != "UMSE_RESEARCH_IDENTITY_V1":
        raise RuntimeError("UMSE_IDENTITY_BAD_SCHEMA")
    cls = doc.get("classification")
    if not isinstance(cls, dict) or not cls:
        raise RuntimeError("UMSE_IDENTITY_EMPTY_CLASSIFICATION")
    bad = sorted(k for k, v in cls.items() if v not in IDENTITIES)
    if bad:
        raise RuntimeError(f"UMSE_IDENTITY_BAD_ASSIGNMENT:{bad}")
    return doc


def source_files(root: Path = SOURCE_ROOT) -> tuple[str, ...]:
    return tuple(sorted(p.name for p in root.glob("*.py") if p.name != "research_identity.py"))


def unclassified_files(root: Path = SOURCE_ROOT, manifest_path: Path = MANIFEST_PATH) -> tuple[str, ...]:
    cls = load_manifest(manifest_path)["classification"]
    return tuple(sorted(name for name in source_files(root) if name not in cls))


def fingerprints(root: Path = SOURCE_ROOT, manifest_path: Path = MANIFEST_PATH) -> Dict[str, dict]:
    doc = load_manifest(manifest_path)
    cls: Mapping[str, str] = doc["classification"]
    missing = unclassified_files(root, manifest_path)
    extras = tuple(sorted(k for k in cls if k not in source_files(root)))
    if missing or extras:
        raise RuntimeError(f"UMSE_IDENTITY_CLASSIFICATION_INCOMPLETE missing={missing} extras={extras}")
    out: Dict[str, dict] = {}
    for ident in IDENTITIES:
        files = {name: _sha(root / name) for name in sorted(k for k, v in cls.items() if v == ident)}
        digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        out[ident.lower()] = {"identity": ident, "digest": digest, "file_count": len(files), "files": files}
    manifest_core = {"schema": doc["schema"], "classification": dict(sorted(cls.items()))}
    out["classification_manifest"] = hashlib.sha256(
        json.dumps(manifest_core, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return out
