"""Read-only operational status of the sealed forward research campaign.

Transport success, stored records, verified evidence and durable backups are
different facts. Never turn a corrupt observation into an empty/healthy sample.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from .forward_oos import DEFAULT_ROOT, MIN_REPORT_N, checkpoint_state, forward_report, records, verify_ledger
from .forward_oos_durable import durability_status


def build_campaign_status(root: Path | str = DEFAULT_ROOT) -> Dict[str, Any]:
    try:
        ledger = verify_ledger(root)
        report = forward_report(root, audit=ledger)
        seal = report.get("campaign_seal") or {}
        rows = records(root)
        storage = durability_status(root)
        enabled = str(os.getenv("FIA_FORWARD_OOS_ENABLED", "1") or "1").strip().lower() not in {"0", "false", "no", "off"}
        valid = bool(ledger.get("ok") and seal.get("ok") and report.get("ok"))
        checks = {"collector_enabled": enabled, "ledger_integrity": bool(ledger.get("ok")),
                  "campaign_seal": bool(seal.get("ok")), "report_integrity": bool(report.get("ok")),
                  "durable_storage": storage.get("durable") is True}
        n = len(rows)
        abstentions = int(ledger.get("abstention_observations") or 0)
        resolved = {h: sum(row.get(h) is not None for row in rows) for h in ("4h", "8h")}
        resolution_times = [(row.get(h) or {}).get("resolved_at_utc")
                            for row in rows for h in ("4h", "8h")]
        verified_n = n if valid else 0
        available = valid and min(resolved.values()) >= MIN_REPORT_N
        reasons = list(ledger.get("issues") or [])
        if not seal.get("ok"):
            reasons.append("CAMPAIGN_SEAL_OR_MODEL_FINGERPRINT_INVALID")
        if report.get("mixed_model_versions"):
            reasons.append("MIXED_MODEL_FINGERPRINTS")
        if not storage.get("durable"):
            reasons.append("FORWARD_BACKUP_INCOMPLETE")
        if not enabled:
            reasons.append("COLLECTOR_DISABLED")
        return {
            "ok": valid, "status": "READY" if all(checks.values()) else "DEGRADED",
            "operational_ok": all(checks.values()), "checks": checks, "issues": reasons,
            "campaign_id": seal.get("campaign_id"),
            "model_fingerprint": (seal.get("sealed_model_fingerprint") or {}).get("digest"),
            "forward_oos_n": n + abstentions, "directional_n": n, "abstention_n": abstentions,
            "counts_basis": "stored observations; only verified counts are validation eligible",
            "verified_directional_n": verified_n,
            "resolved_4h_n": resolved["4h"], "resolved_8h_n": resolved["8h"],
            "verified_resolved_4h_n": resolved["4h"] if valid else 0,
            "verified_resolved_8h_n": resolved["8h"] if valid else 0,
            "milestones": {"next": MIN_REPORT_N, "reached": available,
                           "remaining": max(0, MIN_REPORT_N - (min(resolved.values()) if valid else 0)),
                           "basis": "verified completed observations in both horizons"},
            "last_lock_utc": max((row.get("locked_at_utc") or "" for row in rows), default="") or None,
            "last_resolution_utc": max((t for t in resolution_times if t), default=None),
            "ledger_ok": bool(ledger.get("ok")), "ledger_events": ledger.get("events"),
            "tamper_evident": ledger.get("tamper_evident"), "durability": storage,
            "checkpoint": checkpoint_state(), "metrics_available": available,
            "metrics": {"see": "/api/forward-oos/report"} if available else None,
            "metrics_withheld_reason": (None if available else
                ("INTEGRITY_OR_SEAL_FAILURE: stored records are not verified evidence." if not valid else
                 "At least %d verified resolved observations are required in each horizon." % MIN_REPORT_N)),
            "base_fia": "PRODUCTION_INCUMBENT_UNCHANGED", "predictive_edge": "NOT_PROVEN",
            "shadow_candidate": "NOT_SCORED_YET_NO_UNSEEN_ROWS",
        }
    except Exception as exc:
        return {"ok": False, "operational_ok": False, "status": "UNAVAILABLE",
                "issues": ["FORWARD_STATUS_UNAVAILABLE:" + type(exc).__name__],
                "metrics_available": False, "metrics": None, "ledger_ok": False,
                "predictive_edge": "NOT_PROVEN"}
