"""SIMONS SHADOW LAB V1 — isolated research infrastructure.

This package is intentionally outside ``fia/`` so adding/removing it cannot alter
CLEAR NASDAQ FIA's production model fingerprint surface.
"""
from .lab import (
    LAB_SCHEMA,
    PREDICTIVE_EDGE_STATUS,
    audit_source,
    build_snapshot,
    discover_threshold_candidates,
    freeze_candidate,
    load_snapshot,
    validate_candidate,
    verify_campaign_seal_readonly,
    verify_ledger_readonly,
)

__all__ = [
    "LAB_SCHEMA",
    "PREDICTIVE_EDGE_STATUS",
    "audit_source",
    "build_snapshot",
    "discover_threshold_candidates",
    "freeze_candidate",
    "load_snapshot",
    "validate_candidate",
    "verify_campaign_seal_readonly",
    "verify_ledger_readonly",
]
