from __future__ import annotations

"""Source-pinned read-only adapters for audited upstream research systems.

This module does not import or merge the divergent research branches. It pins
their audited source identities and accepts only their declared research-only
output contracts.
"""

import hashlib
import json
from typing import Any, Mapping

from .adapters import DPCSEView, ShadowHypothesisView, UMSEView

SHADOW_BRANCH_HEAD = "6c52e44b516ec9d707e3acbc3b958fe4dd9d6fe7"
SHADOW_STRICT_CONTRACT_BLOB_SHA = "4db9d5d56b3e80c9c24c8151a49a07bb64a781bf"
SHADOW_REPORTING_BLOB_SHA = "9c7e84d2d594e9416f6edf6dcf8a8048e4d94753"
SHADOW_CAUSAL_DISCOVERY_BLOB_SHA = "ce79a1a9d6378cde83e16d9f9f928b34408bed95"

UMSE_BRANCH_HEAD = "29ef2b56f4a761db2e30c1ac2c104e64884bc497"
UMSE_V2_PIPELINE_BLOB_SHA = "a579cc08e5803400f3c8c503db14ad4492a73139"
UMSE_FORWARD_FILTER_BLOB_SHA = "43e2cf9b41bdffea0aa95b01a2b7fc593ccc8c17"

UPSTREAM_PROVENANCE = {
    "shadow_lab": {
        "branch_head": SHADOW_BRANCH_HEAD,
        "strict_contract_blob": SHADOW_STRICT_CONTRACT_BLOB_SHA,
        "reporting_blob": SHADOW_REPORTING_BLOB_SHA,
        "causal_discovery_blob": SHADOW_CAUSAL_DISCOVERY_BLOB_SHA,
        "status_required": "DISCOVERY_ONLY_NOT_PROVEN",
    },
    "umse": {
        "branch_head": UMSE_BRANCH_HEAD,
        "v2_pipeline_blob": UMSE_V2_PIPELINE_BLOB_SHA,
        "forward_filter_blob": UMSE_FORWARD_FILTER_BLOB_SHA,
        "predictive_mapping_frozen_required": False,
        "predictive_edge_proven_required": False,
        "production_effect_required": False,
    },
}


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _status(value: Any) -> str:
    s = _get(value, "status", "UNKNOWN")
    return str(getattr(s, "value", s))


def shadow_view_from_report(report: Mapping[str, Any]) -> ShadowHypothesisView:
    """Accept only the audited discovery-only Shadow-Lab snapshot contract."""
    if not isinstance(report, Mapping):
        return ShadowHypothesisView(False, (), "", "SHADOW_REPORT_NOT_MAPPING")

    required = (
        report.get("lab_version") == "SIMONS_SHADOW_LAB_V2_HYBRID"
        and report.get("scientific_status") == "DISCOVERY_ONLY_NOT_PROVEN"
        and report.get("lock_time_structural_barrier") is True
        and report.get("automatic_strategy_selection") is False
        and report.get("automatic_production_promotion") is False
        and report.get("predictive_edge_proven") is False
        and report.get("profitability_proven") is False
    )
    digest = _canonical_digest(dict(report))
    if not required:
        return ShadowHypothesisView(False, (), digest, "SHADOW_RESEARCH_CONTRACT_REJECTED")

    transitions = (((report.get("h8") or {}).get("transitions") or {}).get("transitions") or [])
    hypotheses = []
    for item in transitions:
        if not isinstance(item, Mapping):
            continue
        if item.get("status") != "EXPLORATORY_ONLY_NOT_PROVEN":
            continue
        transition = str(item.get("transition") or "").strip()
        if transition:
            hypotheses.append("H8_TRANSITION::" + transition)

    return ShadowHypothesisView(
        available=True,
        hypotheses=tuple(sorted(set(hypotheses))),
        source_digest=digest,
        note="DISCOVERY_ONLY_NOT_PROVEN",
    )


def umse_view_from_v2_diagnostics(diag: Any, *, integrity_pass: bool) -> UMSEView:
    """Adapt UMSE V2 research diagnostics without inventing a predictive mapping."""
    evidence_hash = str(_get(diag, "evidence_hash", "") or "")
    forbidden_escalation = any(
        bool(_get(diag, name, False))
        for name in ("predictive_mapping_frozen", "predictive_edge_proven", "production_effect")
    )
    if forbidden_escalation:
        return UMSEView(False, False, "UMSE_V2_SHADOW_DIAGNOSTICS", (), evidence_hash, "UMSE_STATUS_ESCALATION_REJECTED")

    mechanisms = []
    for name in (
        "queue_survival",
        "orderbook_memory",
        "resistance_field",
        "information_velocity",
        "leadlag_evidence",
        "cross_scale_transport",
    ):
        value = _get(diag, name)
        if value is not None:
            mechanisms.append(f"{name}:{_status(value)}")

    available = bool(evidence_hash) and bool(mechanisms)
    return UMSEView(
        available=available,
        integrity_pass=bool(integrity_pass) and available,
        state_label="UMSE_V2_SHADOW_DIAGNOSTICS",
        mechanisms=tuple(mechanisms),
        source_digest=evidence_hash,
        note="RESEARCH_DIAGNOSTICS_ONLY_NO_PREDICTIVE_MAPPING",
    )


def dpcse_view_from_bootstrap(manifest: Mapping[str, Any]) -> DPCSEView:
    """Adapt the actual DPCSE V2.3 bootstrap/seal status without arming it."""
    candidate = manifest.get("candidate_model")
    frozen = bool(
        isinstance(candidate, Mapping)
        and candidate.get("model_fingerprint")
        and candidate.get("predictive_state_schema_hash")
    )
    digest = _canonical_digest(dict(manifest))
    return DPCSEView(
        status=str(manifest.get("status") or "UNKNOWN"),
        candidate_model_frozen=frozen,
        decision="NO_EDGE",
        p_bull=None,
        p_bear=None,
        locked_rows=int(manifest.get("locked_rows") or manifest.get("locked_rows_at_seal") or 0),
        source_digest=digest,
        predictive_edge=str(manifest.get("predictive_edge") or "NOT_PROVEN"),
    )
