"""Read-only durable Forward-OOS adapter for SIMONS SHADOW LAB V1.

Never imports production write helpers and never executes DDL/DML. It can read
the existing Postgres mirror, verify the event chain, and materialize a
Shadow-Lab-only snapshot. Database credentials are never returned.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .lab import GENESIS, LAB_SCHEMA_VERSION, _row_from_lock, _write_new_json, canonical_bytes, sha256_bytes

_PG_AVAILABLE = False
try:
    import psycopg as _psycopg
    from psycopg.rows import dict_row as _pg_dict_row
    _PG_AVAILABLE = True
except Exception:  # pragma: no cover
    _psycopg = None
    _pg_dict_row = None


def _database_url() -> str:
    return str(os.getenv("DATABASE_URL") or "").strip()


def verify_event_chain(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    issues: List[str] = []
    prev = GENESIS
    expected = 1
    locks: Dict[str, Dict[str, Any]] = {}
    resolutions: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for event in sorted(events, key=lambda e: int(e.get("seq") or 0)):
        seq = int(event.get("seq") or 0)
        if seq != expected:
            issues.append(f"sequence:expected={expected}:got={seq}")
        if str(event.get("prev_event_hash") or "") != prev:
            issues.append(f"chain_prev:seq={seq}")
        claimed = str(event.get("event_hash") or "")
        unsigned = dict(event)
        unsigned.pop("event_hash", None)
        if claimed != sha256_bytes(canonical_bytes(unsigned)):
            issues.append(f"event_hash:seq={seq}")
        et = str(event.get("event_type") or "")
        fid = str(event.get("forecast_id") or "")
        if et == "FORECAST_LOCK":
            if fid in locks:
                issues.append(f"duplicate_forecast_lock:{fid}")
            locks[fid] = event
        elif et in {"RESOLUTION_4H", "RESOLUTION_8H"}:
            hours = 4 if et == "RESOLUTION_4H" else 8
            if fid not in locks:
                issues.append(f"resolution_without_prior_lock:{fid}:{hours}")
            key = (fid, hours)
            if key in resolutions:
                issues.append(f"duplicate_resolution:{fid}:{hours}")
            resolutions[key] = event
        prev = claimed
        expected += 1
    return {
        "ok": not issues,
        "events": len(events),
        "forecast_locks": len(locks),
        "resolution_events": len(resolutions),
        "head_event_hash": prev,
        "issues": issues,
        "production_modified": False,
        "source": "DURABLE_READ_ONLY",
    }


def rows_from_events(events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    audit = verify_event_chain(events)
    if not audit["ok"]:
        raise RuntimeError("durable event integrity failure: " + ";".join(audit["issues"]))
    locks: Dict[str, Dict[str, Any]] = {}
    resolutions: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for event in events:
        et = str(event.get("event_type") or "")
        fid = str(event.get("forecast_id") or "")
        if et == "FORECAST_LOCK":
            locks[fid] = event
        elif et in {"RESOLUTION_4H", "RESOLUTION_8H"}:
            resolutions[(fid, 4 if et == "RESOLUTION_4H" else 8)] = event
    return sorted((_row_from_lock(lock, resolutions) for lock in locks.values()), key=lambda row: str(row.get("locked_at_utc") or ""))


class DurableForwardOOSReader:
    """SELECT-only adapter with PostgreSQL transaction-level read-only mode."""
    def __init__(self, database_url: Optional[str] = None):
        self._dsn = str(database_url or _database_url()).strip()

    def configured(self) -> bool:
        return bool(self._dsn) and _PG_AVAILABLE

    def _connect(self):
        if not self.configured():
            raise RuntimeError("durable reader is not configured")
        return _psycopg.connect(self._dsn, row_factory=_pg_dict_row, connect_timeout=10, options="-c default_transaction_read_only=on")

    def campaigns(self) -> List[Dict[str, Any]]:
        sql = """
        SELECT campaign_id,
               COUNT(*) FILTER (WHERE is_test=FALSE) AS production_events,
               COUNT(*) FILTER (WHERE is_test=FALSE AND event_type='FORECAST_LOCK') AS locks,
               COUNT(*) FILTER (WHERE is_test=FALSE AND event_type IN ('RESOLUTION_4H','RESOLUTION_8H')) AS resolutions,
               MAX(mirrored_at) FILTER (WHERE is_test=FALSE) AS last_mirrored_at
        FROM forward_oos_events GROUP BY campaign_id
        ORDER BY MAX(mirrored_at) DESC NULLS LAST
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall() or []
        return [{
            "campaign_id": str(r.get("campaign_id") or ""),
            "production_events": int(r.get("production_events") or 0),
            "forecast_locks": int(r.get("locks") or 0),
            "resolution_events": int(r.get("resolutions") or 0),
            "last_mirrored_at": str(r.get("last_mirrored_at") or ""),
        } for r in rows]

    def read_events(self, campaign_id: str) -> List[Dict[str, Any]]:
        sql = "SELECT seq, canonical_json FROM forward_oos_events WHERE campaign_id=%s AND is_test=FALSE ORDER BY seq ASC"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (str(campaign_id),))
                rows = cur.fetchall() or []
        events: List[Dict[str, Any]] = []
        for row in rows:
            event = json.loads(bytes(row["canonical_json"]).decode("utf-8"))
            if not isinstance(event, dict):
                raise RuntimeError("durable canonical_json is not an object")
            events.append(event)
        return events

    def audit(self, campaign_id: str) -> Dict[str, Any]:
        out = verify_event_chain(self.read_events(campaign_id))
        out.update({
            "campaign_id": campaign_id,
            "database_credentials_exposed": False,
            "evidence_file_bytes_verified": False,
            "evidence_hashes_preserved_in_lock_events": True,
        })
        return out

    def create_snapshot(self, campaign_id: str, lab_root: Path, now: Optional[datetime] = None) -> Dict[str, Any]:
        events = self.read_events(campaign_id)
        audit = verify_event_chain(events)
        if not audit["ok"]:
            raise RuntimeError("durable source integrity failure")
        rows = rows_from_events(events)
        now = now or datetime.now(timezone.utc)
        core = {
            "schema_version": LAB_SCHEMA_VERSION,
            "source_mode": "DURABLE_POSTGRES_READ_ONLY",
            "campaign_id": campaign_id,
            "created_at_utc": now.astimezone(timezone.utc).isoformat(),
            "source_head_event_hash": audit["head_event_hash"],
            "row_count": len(rows),
            "completed_4h": sum(1 for r in rows if "4h" in (r.get("outcomes") or {})),
            "completed_8h": sum(1 for r in rows if "8h" in (r.get("outcomes") or {})),
            "forecast_ids": [r.get("forecast_id") for r in rows],
            "rows_sha256": sha256_bytes(canonical_bytes(rows)),
            "event_chain_verified": True,
            "evidence_file_bytes_verified": False,
            "evidence_hashes_preserved_in_events": True,
            "production_modified": False,
            "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
        }
        core["snapshot_id"] = "SSL1-DUR-" + sha256_bytes(canonical_bytes(core))[:20]
        manifest = dict(core)
        manifest["manifest_sha256"] = sha256_bytes(canonical_bytes(core))
        root = Path(lab_root) / "snapshots" / core["snapshot_id"]
        _write_new_json(root / "manifest.json", manifest)
        _write_new_json(root / "rows.json", {"rows": rows, "rows_sha256": core["rows_sha256"]})
        return manifest
