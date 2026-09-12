"""Integrity manifest and final readiness audit for SIMONS SHADOW LAB V1."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .causal_candidate import CausalCandidateLab
from .experiment_registry import ExperimentRegistry
from .lab import ShadowLab, canonical_bytes, sha256_bytes, sha256_file


def package_manifest(package_root: Path) -> Dict[str, Any]:
    root = Path(package_root)
    files: Dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".md", ".json"} and "__pycache__" not in path.parts:
            files[str(path.relative_to(root))] = sha256_file(path)
    return {
        "algorithm": "sha256",
        "files": files,
        "file_count": len(files),
        "digest": sha256_bytes(canonical_bytes(files)),
    }


def audit_lab_storage(lab_root: Path, source_root: Optional[Path] = None) -> Dict[str, Any]:
    root = Path(lab_root)
    issues: List[str] = []
    source = Path(source_root or ".")
    core = ShadowLab(source, root)

    snapshot_ids = []
    snapshots = root / "snapshots"
    if snapshots.exists():
        for item in sorted(p for p in snapshots.iterdir() if p.is_dir()):
            try:
                core.load_snapshot(item.name)
                snapshot_ids.append(item.name)
            except Exception as exc:
                issues.append(f"snapshot:{item.name}:{type(exc).__name__}")

    causal = CausalCandidateLab(source, root)
    causal_ids = []
    croot = root / "causal_candidates"
    if croot.exists():
        for path in sorted(croot.glob("*.json")):
            cid = path.stem
            try:
                causal.load(cid)
                causal._events(cid)
                causal_ids.append(cid)
            except Exception as exc:
                issues.append(f"causal_candidate:{cid}:{type(exc).__name__}")

    standard_ids = []
    sroot = root / "candidates"
    if sroot.exists():
        for path in sorted(sroot.glob("*.json")):
            cid = path.stem
            try:
                core.load_candidate(cid)
                core._shadow_events(cid)
                standard_ids.append(cid)
            except Exception as exc:
                issues.append(f"candidate:{cid}:{type(exc).__name__}")

    try:
        experiment_audit = ExperimentRegistry(root).audit()
    except Exception as exc:
        experiment_audit = {"ok": False, "error_type": type(exc).__name__}
        issues.append(f"experiment_registry:{type(exc).__name__}")

    return {
        "ok": not issues,
        "engineering_readiness": "PASS" if not issues else "FAIL",
        "issues": issues,
        "snapshots_verified": len(snapshot_ids),
        "standard_candidates_verified": len(standard_ids),
        "causal_candidates_verified": len(causal_ids),
        "experiment_registry": experiment_audit,
        "automatic_production_promotion": False,
        "predictive_edge_proven": False,
        "profitability_proven": False,
        "scientific_status": "RESEARCH_INFRASTRUCTURE_READY_EDGE_NOT_PROVEN" if not issues else "RESEARCH_INFRASTRUCTURE_NOT_READY",
        "production_modified": False,
    }
