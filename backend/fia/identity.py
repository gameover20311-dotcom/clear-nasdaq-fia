# CLEAR NASDAQ — THREE SCIENTIFIC IDENTITIES  (A7 / Amendment A s.26)
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parents[1]
CLASSIFICATION_PATH = Path(__file__).resolve().parent / "identity_classification.json"

IDENTITY_SCHEMA_VERSION = "FIA_IDENTITY_V2_EFFECTIVE_CONFIG"
CLASSIFICATION_SCHEMA = "FIA_IDENTITY_CLASSIFICATION_V1"
IDENTITIES = ("MODEL", "PROTOCOL", "INFRASTRUCTURE")
EXPECTED_CLASSIFICATION_MANIFEST_ID = (
    "1e847b0588b21dc2d361e68f33d8009df4e7647efb340af36885da47ffcabca5"
)

# Only non-secret, scientifically material runtime controls belong here.  A
# change in these values changes which observations are eligible and therefore
# must change the PROTOCOL identity even when source bytes are identical.
_SCIENTIFIC_PROTOCOL_ENV_DEFAULTS = {
    "FIA_FORWARD_OOS_CHECKPOINT_ET": "13:00",
    "FIA_FORWARD_OOS_GRACE_MINUTES": "10",
}


class ClassificationIntegrityError(RuntimeError):
    pass


_CLS: Optional[Dict[str, Any]] = None


def compute_classification_manifest_id(schema: str, classification: Dict[str, str]) -> str:
    core = {"schema": schema, "classification": dict(classification)}
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _classification() -> Dict[str, Any]:
    global _CLS
    if _CLS is None:
        if not CLASSIFICATION_PATH.exists():
            raise ClassificationIntegrityError(f"CLASSIFICATION_MISSING: {CLASSIFICATION_PATH}")
        try:
            doc = json.loads(CLASSIFICATION_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ClassificationIntegrityError(f"CLASSIFICATION_MALFORMED_JSON: {exc}") from exc
        if doc.get("schema") != CLASSIFICATION_SCHEMA:
            raise ClassificationIntegrityError(
                f"CLASSIFICATION_INVALID_SCHEMA: got {doc.get('schema')!r}")
        cls = doc.get("classification")
        if not isinstance(cls, dict) or not cls:
            raise ClassificationIntegrityError("CLASSIFICATION_INVALID_SCHEMA: empty classification")
        bad = sorted(k for k, v in cls.items() if v not in IDENTITIES)
        if bad:
            raise ClassificationIntegrityError(f"CLASSIFICATION_INVALID_IDENTITY: {bad[:5]}")
        recomputed = compute_classification_manifest_id(doc["schema"], cls)
        if doc.get("manifest_id") != recomputed:
            raise ClassificationIntegrityError(
                f"CLASSIFICATION_MANIFEST_MISMATCH: stored={doc.get('manifest_id')!r} "
                f"recomputed={recomputed!r}")
        if recomputed != EXPECTED_CLASSIFICATION_MANIFEST_ID:
            raise ClassificationIntegrityError(
                f"CLASSIFICATION_NOT_THE_PINNED_MANIFEST: pinned="
                f"{EXPECTED_CLASSIFICATION_MANIFEST_ID!r} found={recomputed!r}")
        _CLS = doc
    return _CLS


def classification_manifest_id() -> str:
    _classification()
    return EXPECTED_CLASSIFICATION_MANIFEST_ID


def blocked_pending_split() -> Dict[str, Any]:
    return dict(_classification().get("blocked_pending_split") or {})


def resolved_classifications() -> Dict[str, Any]:
    return dict(_classification().get("resolved") or {})


def classification_map() -> Dict[str, str]:
    return dict(_classification()["classification"])


def review_required() -> Dict[str, str]:
    return dict(_classification().get("review_required") or {})


def scope_files(backend_root: Path = BACKEND) -> List[str]:
    from .forward_oos import _production_fingerprint_files
    return list(_production_fingerprint_files(backend_root))


def unclassified_files(backend_root: Path = BACKEND) -> List[str]:
    cls = classification_map()
    return sorted(r for r in scope_files(backend_root) if r not in cls)


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def effective_scientific_protocol_config() -> Dict[str, str]:
    """Canonical, non-secret protocol configuration affecting eligibility.

    Values are normalized exactly as the Forward-OOS protocol reads them.  This
    function intentionally excludes credentials, URLs, logging controls and
    other operational settings that do not change scientific meaning.
    """
    raw_checkpoint = str(os.getenv("FIA_FORWARD_OOS_CHECKPOINT_ET", "13:00") or "13:00").strip()
    raw_grace = str(os.getenv("FIA_FORWARD_OOS_GRACE_MINUTES", "10") or "10").strip()

    # Validate and canonicalize checkpoint without importing forward_oos here
    # (avoids an identity->protocol import cycle).
    try:
        hh_s, mm_s = raw_checkpoint.split(":", 1)
        hh, mm = int(hh_s), int(mm_s)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError
    except Exception as exc:
        raise RuntimeError("INVALID_SCIENTIFIC_CONFIG:FIA_FORWARD_OOS_CHECKPOINT_ET") from exc
    try:
        grace = max(1, int(raw_grace))
    except Exception as exc:
        raise RuntimeError("INVALID_SCIENTIFIC_CONFIG:FIA_FORWARD_OOS_GRACE_MINUTES") from exc

    return {
        "FIA_FORWARD_OOS_CHECKPOINT_ET": f"{hh:02d}:{mm:02d}",
        "FIA_FORWARD_OOS_GRACE_MINUTES": str(grace),
    }


def fingerprint(identity: str, backend_root: Path = BACKEND) -> Dict[str, Any]:
    """Deterministic digest over assigned source plus material effective config."""
    ident = str(identity).upper()
    if ident not in IDENTITIES:
        raise ValueError(f"unknown identity {identity!r}; expected one of {IDENTITIES}")
    missing = unclassified_files(backend_root)
    if missing:
        raise RuntimeError(
            "IDENTITY_CLASSIFICATION_INCOMPLETE: "
            + ", ".join(missing[:8])
            + (" ..." if len(missing) > 8 else "")
        )
    cls = classification_map()
    rels = sorted(r for r in scope_files(backend_root) if cls[r] == ident)
    files = {rel: _sha256_file(backend_root / rel) for rel in rels}

    bound: Dict[str, Any] = {"files": files}
    effective_config = None
    if ident == "PROTOCOL":
        effective_config = effective_scientific_protocol_config()
        bound["effective_scientific_config"] = effective_config

    out = {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "identity": ident,
        "algorithm": "sha256",
        "digest": hashlib.sha256(_canonical(bound)).hexdigest(),
        "file_count": len(files),
        "files": files,
    }
    if effective_config is not None:
        out["effective_scientific_config"] = effective_config
        out["config_bound"] = True
    return out


def model_fingerprint_v2(backend_root: Path = BACKEND) -> Dict[str, Any]:
    return fingerprint("MODEL", backend_root)


def protocol_fingerprint(backend_root: Path = BACKEND) -> Dict[str, Any]:
    return fingerprint("PROTOCOL", backend_root)


def infrastructure_fingerprint(backend_root: Path = BACKEND) -> Dict[str, Any]:
    return fingerprint("INFRASTRUCTURE", backend_root)


def all_fingerprints(backend_root: Path = BACKEND, include_files: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "classification_schema": _classification().get("schema"),
        "classification_manifest_id": classification_manifest_id(),
        "review_required": sorted(review_required().keys()),
        "blocked_pending_split": sorted(blocked_pending_split().get("coverage", {}).keys())
        and blocked_pending_split().get("status"),
    }
    for ident in IDENTITIES:
        fp = fingerprint(ident, backend_root)
        if not include_files:
            fp.pop("files", None)
        out[ident.lower()] = fp
    from .forward_oos import model_fingerprint as _legacy
    legacy = _legacy(backend_root)
    out["legacy_deployment_fingerprint"] = {
        "note": "Whole-backend digest used by the sealed V6 campaign. Retained unchanged so that "
                "historical seal record stays readable. NOT the scientific model identity.",
        "digest": legacy.get("digest"),
        "file_count": legacy.get("file_count"),
    }
    return out


def historical_identity_available(campaign_seal: Dict[str, Any]) -> Dict[str, Any]:
    seal = campaign_seal or {}
    present = {
        ident.lower(): bool((seal.get(f"{ident.lower()}_fingerprint") or {}).get("digest"))
        for ident in IDENTITIES
    }
    return {
        "campaign_id": seal.get("campaign_id"),
        "three_identity_split_recorded": all(present.values()),
        "available": present,
        "legacy_whole_backend_digest": (seal.get("model_fingerprint") or {}).get("digest"),
        "status": ("AVAILABLE" if all(present.values())
                   else "UNAVAILABLE_SEALED_BEFORE_IDENTITY_SPLIT"),
        "reconstructed": False,
    }
