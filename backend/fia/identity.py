# CLEAR NASDAQ — THREE SCIENTIFIC IDENTITIES  (A7 / Amendment A s.26)
#
# WHY
# ---
# The Forward-OOS campaign was re-sealed 24 times between 3 and 8 September,
# every time with 0 forecast locks, because ONE fingerprint covered the whole
# backend. Adding fia/auth_api.py invalidated a campaign whose model had not
# changed by a single coefficient. A commit hash is not the scientific identity
# of an experiment.
#
# Amendment A s.26 therefore splits identity three ways:
#
#   MODEL           anything that can change the forecast itself — weights,
#                   features/transforms, probability generation, aggregation,
#                   abstention decision logic.
#   PROTOCOL        anything that changes WHICH observations are admitted or
#                   HOW they are evaluated — checkpoints, horizon semantics,
#                   source eligibility, fallback/proxy rules, staleness rules,
#                   evidence requirements, resolution rules, baseline
#                   definition, outcome definition, validation eligibility,
#                   primary statistical protocol.
#   INFRASTRUCTURE  machinery that must NOT alter scientific meaning — storage
#                   adapters, evidence mirroring, recovery plumbing, API
#                   transport, logging, deployment wiring.
#
# HOW
# ---
# Classification is an EXPLICIT per-file registry (identity_classification.json),
# never a heuristic on filenames. Heuristics drift silently; an explicit list can
# be audited and diffed. Every file in the fingerprint scope must appear exactly
# once, and an unclassified file is a hard error rather than a silent default —
# so a new module cannot slip into the experiment unclassified.
#
# HONESTY CONSTRAINTS
# -------------------
#  * The legacy whole-backend digest in fia/forward_oos.py is NOT changed here.
#    The sealed V6 campaign was pinned with it and that record stays readable.
#    This module adds the split; adopting it for sealing is a successor-campaign
#    decision, which has not been taken.
#  * No historical fingerprint is reconstructed. Campaigns sealed before the
#    split simply have no MODEL/PROTOCOL/INFRASTRUCTURE digests, and
#    historical_identity_available() says so instead of inventing them.
#  * Entries listed under review_required in the registry are PROPOSED
#    assignments and must be signed off before any successor seal.
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parents[1]
CLASSIFICATION_PATH = Path(__file__).resolve().parent / "identity_classification.json"

IDENTITY_SCHEMA_VERSION = "FIA_IDENTITY_V1"
CLASSIFICATION_SCHEMA = "FIA_IDENTITY_CLASSIFICATION_V1"
IDENTITIES = ("MODEL", "PROTOCOL", "INFRASTRUCTURE")

# A7.2 — the three digests are only meaningful alongside the manifest that
# produced them. A successor seal must be able to prove WHICH classification
# generated MODEL/PROTOCOL/INFRASTRUCTURE, otherwise the same file set could be
# re-partitioned later and the digests silently mean something different.
# Pinned in code and stored in the JSON; both change together, deliberately.
EXPECTED_CLASSIFICATION_MANIFEST_ID = (
    "0d9164edf52031460d24e875612204ac9e0f984073f6d39b586769cd22823e0e"
)


class ClassificationIntegrityError(RuntimeError):
    """Raised when the classification manifest cannot be trusted."""


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
    """Modules the owner decided to split, where the split is not yet verifiable."""
    return dict(_classification().get("blocked_pending_split") or {})


def resolved_classifications() -> Dict[str, Any]:
    """Evidence-backed resolutions, with the call paths that produced them."""
    return dict(_classification().get("resolved") or {})


def classification_map() -> Dict[str, str]:
    return dict(_classification()["classification"])


def review_required() -> Dict[str, str]:
    """Proposed assignments awaiting human sign-off."""
    return dict(_classification().get("review_required") or {})


def scope_files(backend_root: Path = BACKEND) -> List[str]:
    """The file set the existing production fingerprint covers."""
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


def fingerprint(identity: str, backend_root: Path = BACKEND) -> Dict[str, Any]:
    """Deterministic digest over exactly the files assigned to one identity.

    Fail-closed: if any file in scope is unclassified, this raises rather than
    quietly attributing it to one identity or dropping it from all three.
    """
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
    return {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "identity": ident,
        "algorithm": "sha256",
        "digest": hashlib.sha256(_canonical(files)).hexdigest(),
        "file_count": len(files),
        "files": files,
    }


def model_fingerprint_v2(backend_root: Path = BACKEND) -> Dict[str, Any]:
    return fingerprint("MODEL", backend_root)


def protocol_fingerprint(backend_root: Path = BACKEND) -> Dict[str, Any]:
    return fingerprint("PROTOCOL", backend_root)


def infrastructure_fingerprint(backend_root: Path = BACKEND) -> Dict[str, Any]:
    return fingerprint("INFRASTRUCTURE", backend_root)


def all_fingerprints(backend_root: Path = BACKEND, include_files: bool = False) -> Dict[str, Any]:
    """All three identities, individually reportable."""
    out: Dict[str, Any] = {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "classification_schema": _classification().get("schema"),
        # A7.2 — which manifest produced these digests.
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
        "note": "Whole-backend digest used by the sealed V6 campaign. Retained "
                "unchanged so that historical seal record stays readable. NOT the "
                "scientific model identity.",
        "digest": legacy.get("digest"),
        "file_count": legacy.get("file_count"),
    }
    return out


def historical_identity_available(campaign_seal: Dict[str, Any]) -> Dict[str, Any]:
    """Report honestly whether a past seal carries the three identities.

    Campaigns sealed before this split recorded only the whole-backend digest.
    Their MODEL/PROTOCOL/INFRASTRUCTURE identities are UNAVAILABLE and are never
    reconstructed after the fact.
    """
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
