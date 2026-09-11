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
IDENTITIES = ("MODEL", "PROTOCOL", "INFRASTRUCTURE")

_CLS: Optional[Dict[str, Any]] = None


def _classification() -> Dict[str, Any]:
    global _CLS
    if _CLS is None:
        _CLS = json.loads(CLASSIFICATION_PATH.read_text(encoding="utf-8"))
    return _CLS


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
        "review_required": sorted(review_required().keys()),
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
