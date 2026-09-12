from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Mapping


PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parents[1]
CLASSIFICATION_PATH = ROOT_DIR / "spec" / "identity_classification_v1.json"
VALID_IDENTITIES = {"MODEL", "PROTOCOL", "INFRASTRUCTURE"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classification_manifest() -> Mapping[str, str]:
    payload = json.loads(CLASSIFICATION_PATH.read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise RuntimeError("V2 identity classification must contain a non-empty files map")
    out: Dict[str, str] = {}
    for name, identity in files.items():
        if identity not in VALID_IDENTITIES:
            raise RuntimeError(f"invalid identity class for {name}: {identity}")
        out[str(name)] = str(identity)
    return out


def source_files() -> tuple[str, ...]:
    return tuple(sorted(p.name for p in PACKAGE_DIR.glob("*.py") if p.is_file()))


def unclassified_files() -> tuple[str, ...]:
    manifest = classification_manifest()
    return tuple(sorted(set(source_files()) - set(manifest)))


def missing_classified_files() -> tuple[str, ...]:
    manifest = classification_manifest()
    return tuple(sorted(set(manifest) - set(source_files())))


def _digest_file_map(files: Mapping[str, str]) -> str:
    payload = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fingerprints() -> Mapping[str, object]:
    """Return fail-closed V2 scientific identities.

    Every Python source file under this V2 package must be explicitly classified.
    `research_identity.py` itself is deliberately included, closing the V1 layout
    limitation where identity machinery sat outside its own fingerprint scope.
    """

    unexpected = unclassified_files()
    missing = missing_classified_files()
    if unexpected or missing:
        raise RuntimeError(
            f"V2 identity classification mismatch: unclassified={unexpected}, missing={missing}"
        )

    manifest = classification_manifest()
    grouped: Dict[str, Dict[str, str]] = {identity: {} for identity in VALID_IDENTITIES}
    for filename, identity in manifest.items():
        grouped[identity][filename] = _sha256(PACKAGE_DIR / filename)

    result: Dict[str, object] = {}
    for key in ("MODEL", "PROTOCOL", "INFRASTRUCTURE"):
        file_map = dict(sorted(grouped[key].items()))
        result[key.lower()] = {
            "identity": key,
            "file_count": len(file_map),
            "files": file_map,
            "digest": _digest_file_map(file_map),
        }

    result["classification_manifest"] = _sha256(CLASSIFICATION_PATH)
    return result
