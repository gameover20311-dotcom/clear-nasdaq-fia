from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Mapping


PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parents[1]
CLASSIFICATION_PATH = ROOT_DIR / "spec" / "identity_classification_v1.json"
V1_PACKAGE_DIR = ROOT_DIR.parent / "umse_master" / "src" / "umse_master"
VALID_IDENTITIES = {"MODEL", "PROTOCOL", "INFRASTRUCTURE"}
IDENTITY_SCHEMA = "UMSE_V2_IDENTITY_TRANSITIVE_V2"


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


def transitive_v1_files() -> tuple[Path, ...]:
    """Conservative fail-closed binding for V2's imported V1 scientific code.

    V2 imports `umse_master.*` modules, which in turn import one another.  The
    previous V2 fingerprints covered only package-local V2 source, so a V1
    mutation could change V2 behaviour without changing any V2 identity.  Until
    a separately audited fine-grained dependency manifest exists, binding the
    complete sibling V1 source package is safer than silently omitting a live
    scientific dependency.
    """
    if not V1_PACKAGE_DIR.is_dir():
        raise RuntimeError(f"V1 dependency package missing: {V1_PACKAGE_DIR}")
    files = tuple(sorted(
        p for p in V1_PACKAGE_DIR.rglob("*.py")
        if p.is_file() and "__pycache__" not in p.parts
    ))
    if not files:
        raise RuntimeError("V1 dependency package contains no Python source")
    return files


def _digest_file_map(files: Mapping[str, str]) -> str:
    payload = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fingerprints() -> Mapping[str, object]:
    """Return fail-closed V2 scientific identities including V1 dependencies.

    Every Python source file under the V2 package is explicitly classified.
    Every identity also binds the complete V1 source package because V2 runtime
    scientific behaviour depends transitively on V1 modules.  This deliberately
    over-invalidates rather than allowing behaviour to drift under an unchanged
    V2 digest.
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
        grouped[identity]["v2/" + filename] = _sha256(PACKAGE_DIR / filename)

    v1_map = {
        "v1_dependency/" + str(path.relative_to(V1_PACKAGE_DIR)): _sha256(path)
        for path in transitive_v1_files()
    }
    for identity in VALID_IDENTITIES:
        grouped[identity].update(v1_map)

    result: Dict[str, object] = {"schema": IDENTITY_SCHEMA}
    for key in ("MODEL", "PROTOCOL", "INFRASTRUCTURE"):
        file_map = dict(sorted(grouped[key].items()))
        result[key.lower()] = {
            "identity": key,
            "file_count": len(file_map),
            "local_v2_file_count": sum(1 for name in file_map if name.startswith("v2/")),
            "bound_v1_dependency_file_count": len(v1_map),
            "transitive_v1_bound": True,
            "files": file_map,
            "digest": _digest_file_map(file_map),
        }

    result["classification_manifest"] = _sha256(CLASSIFICATION_PATH)
    return result