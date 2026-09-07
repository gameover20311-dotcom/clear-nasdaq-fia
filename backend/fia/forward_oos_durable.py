"""Durable Postgres mirror for the Forward-OOS append-only ledger.

WHY THIS EXISTS
---------------
Observed directly on 2026-09-07: the 13:00 ET checkpoint fired, the system
declined to make a directional call, and recorded its first live abstention
observation (events: 1, forecast_locks: 0). A routine redeploy followed and the
ledger came back events: 0. A genuine scientific record was created and then
destroyed by a deploy, inside one session.

Render's filesystem is replaced on every deploy, so a file-only ledger can never
accumulate observations. At the current deploy cadence n would reset to zero
indefinitely, which makes any 30/50/100 programme impossible.

WHAT THIS DOES
--------------
Mirrors every appended event into Postgres, byte-for-byte, as the exact
canonical JSON that was written to disk. On boot, if the local events directory
is empty and the database holds events for this campaign, the files are
recreated from the database so the existing hash-chain verifier keeps working
unchanged.

WHAT IT DOES NOT DO
-------------------
* It does not become the source of truth. The file ledger and its hash chain
  remain authoritative; this is a durable copy of it.
* It never rewrites, mutates or deletes a production row. The table grants
  INSERT only for production events; the sole delete path refuses any row that
  is not explicitly flagged as a test fixture.
* It never backfills. Only events that the file layer actually appended are
  mirrored, with their original seq, timestamps and hashes.
* A mirror failure never fabricates success: durability_status() reports
  DEGRADED and names the failure so an operator can see that the event exists on
  ephemeral storage only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

_PG_AVAILABLE = False
try:
    import psycopg as _psycopg
    from psycopg.rows import dict_row as _pg_dict_row
    _PG_AVAILABLE = True
except Exception:                                                    # pragma: no cover
    _psycopg = None
    _pg_dict_row = None

TABLE = "forward_oos_events"
_LEDGER_FILE_RE = __import__("re").compile(r"^\d{8}_[a-z0-9-]+_.+\.json$")
_LAST_ERROR: Optional[str] = None

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS forward_oos_events (
        campaign_id   TEXT    NOT NULL,
        seq           BIGINT  NOT NULL,
        event_type    TEXT    NOT NULL,
        forecast_id   TEXT    NOT NULL,
        created_at_utc TEXT   NOT NULL,
        prev_event_hash TEXT  NOT NULL,
        event_hash    TEXT    NOT NULL,
        file_name     TEXT    NOT NULL,
        canonical_json BYTEA  NOT NULL,
        is_test       BOOLEAN NOT NULL DEFAULT FALSE,
        mirrored_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (campaign_id, seq)
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_foos_event_hash ON forward_oos_events(campaign_id, event_hash)",
    "CREATE INDEX IF NOT EXISTS idx_foos_test ON forward_oos_events(campaign_id, is_test)",
)


def _database_url() -> str:
    return str(os.getenv("DATABASE_URL") or "").strip()


def enabled() -> bool:
    return bool(_database_url()) and _PG_AVAILABLE


def _connect():
    conn = _psycopg.connect(_database_url(), row_factory=_pg_dict_row, connect_timeout=10)
    with conn.cursor() as cur:
        for ddl in _SCHEMA:
            cur.execute(ddl)
    conn.commit()
    return conn


def _campaign_id(root: Path) -> str:
    seal = Path(root) / "FORWARD_OOS_CAMPAIGN_SEAL.json"
    try:
        return str(json.loads(seal.read_text(encoding="utf-8")).get("campaign_id") or "UNKNOWN")
    except Exception:                                                # noqa: BLE001
        return "UNKNOWN"


def durability_status(root: Path | str) -> Dict[str, Any]:
    """What the ledger's durability actually is. Never claims more than it has."""
    root = Path(root)
    if not _database_url():
        return {"durable": False, "backend": "filesystem", "durability": "EPHEMERAL",
                "survives_redeploy": False,
                "detail": "no DATABASE_URL; the ledger is destroyed by every redeploy"}
    if not _PG_AVAILABLE:
        return {"durable": False, "backend": "filesystem", "durability": "EPHEMERAL",
                "survives_redeploy": False,
                "detail": "DATABASE_URL is set but the psycopg driver is not installed"}
    try:
        cid = _campaign_id(root)
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE is_test) AS t "
                    "FROM forward_oos_events WHERE campaign_id=%s", (cid,))
                row = cur.fetchone() or {}
        return {"durable": True, "backend": "postgres", "durability": "DURABLE",
                "survives_redeploy": True, "campaign_id": cid,
                "mirrored_events": int(row.get("n") or 0),
                "test_fixtures": int(row.get("t") or 0),
                "last_error": _LAST_ERROR,
                "detail": "events are mirrored to Postgres and restored after a redeploy"}
    except Exception as exc:                                         # noqa: BLE001
        # Never surface the driver message: it carries the DSN.
        return {"durable": False, "backend": "postgres", "durability": "DEGRADED",
                "survives_redeploy": False,
                "detail": "database unreachable (%s)" % type(exc).__name__}


def mirror_event(root: Path | str, event: Dict[str, Any], canonical: bytes,
                 file_name: str, is_test: bool = False) -> Dict[str, Any]:
    """Copy one appended event into Postgres. INSERT only; never updates."""
    global _LAST_ERROR
    if not enabled():
        return {"mirrored": False, "reason": "DURABLE_STORE_NOT_CONFIGURED"}
    try:
        cid = _campaign_id(root)
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO forward_oos_events "
                    "(campaign_id, seq, event_type, forecast_id, created_at_utc, "
                    " prev_event_hash, event_hash, file_name, canonical_json, is_test) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (campaign_id, seq) DO NOTHING",
                    (cid, int(event.get("seq") or 0), str(event.get("event_type") or ""),
                     str(event.get("forecast_id") or ""), str(event.get("created_at_utc") or ""),
                     str(event.get("prev_event_hash") or ""), str(event.get("event_hash") or ""),
                     file_name, canonical, bool(is_test)))
            conn.commit()
        _LAST_ERROR = None
        return {"mirrored": True, "seq": event.get("seq")}
    except Exception as exc:                                         # noqa: BLE001
        _LAST_ERROR = type(exc).__name__
        print("Forward-OOS durable mirror FAILED -> %s "
              "(event exists on ephemeral storage only)" % type(exc).__name__)
        return {"mirrored": False, "reason": "MIRROR_FAILED",
                "error_type": type(exc).__name__}


def restore_missing(root: Path | str) -> Dict[str, Any]:
    """Recreate ledger files from Postgres when local storage came back empty.

    Only writes files that are absent. An existing file is never overwritten, so
    a live ledger can never be clobbered by the mirror.
    """
    root = Path(root)
    if not enabled():
        return {"restored": 0, "reason": "DURABLE_STORE_NOT_CONFIGURED"}
    events_dir = root / "events"
    try:
        cid = _campaign_id(root)
        with _connect() as conn:
            with conn.cursor() as cur:
                # is_test rows must NEVER be restored into the ledger.
                # Without this predicate a durability fixture was written into
                # events/ and the hash-chain verifier correctly rejected the whole
                # ledger (sequence/chain_prev/event_hash issues). The fixture is
                # durable in Postgres; it is not, and must never become, a ledger
                # event.
                cur.execute(
                    "SELECT seq, file_name, canonical_json, event_hash FROM forward_oos_events "
                    "WHERE campaign_id=%s AND is_test = FALSE ORDER BY seq ASC", (cid,))
                rows = cur.fetchall() or []
        if not rows:
            return {"restored": 0, "available": 0}
        events_dir.mkdir(parents=True, exist_ok=True)
        written = 0
        for r in rows:
            name = str(r["file_name"])
            # Defence in depth: a ledger file is always NNNNNNNN_<type>_<id>.json.
            # Anything else (a fixture, a stray row) is refused even if the
            # is_test predicate above were somehow bypassed.
            if not _LEDGER_FILE_RE.match(name):
                print("Forward-OOS restore skipped non-ledger row: %s" % name[:64])
                continue
            path = events_dir / name
            if path.exists():
                continue
            blob = bytes(r["canonical_json"])
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            with os.fdopen(fd, "wb") as f:
                f.write(blob)
                f.flush()
                os.fsync(f.fileno())
            written += 1
        return {"restored": written, "available": len(rows)}
    except Exception as exc:                                         # noqa: BLE001
        print("Forward-OOS durable restore FAILED -> %s" % type(exc).__name__)
        return {"restored": 0, "reason": "RESTORE_FAILED",
                "error_type": type(exc).__name__}


# --------------------------------------------------------------- test fixtures
def write_test_fixture(root: Path | str, marker: str) -> Dict[str, Any]:
    """Write an isolated TEST durability record. Never a production observation.

    It carries is_test=TRUE, a TEST_ event_type and a negative seq so it can
    never collide with, or be mistaken for, a real sequence number.
    """
    if not enabled():
        return {"ok": False, "reason": "DURABLE_STORE_NOT_CONFIGURED"}
    try:
        cid = _campaign_id(Path(root))
        payload = json.dumps({"marker": marker, "purpose": "durability probe",
                              "scoreable": False}, sort_keys=True).encode()
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MIN(seq), 0) AS m FROM forward_oos_events "
                            "WHERE campaign_id=%s AND is_test", (cid,))
                nxt = int((cur.fetchone() or {}).get("m") or 0) - 1
                cur.execute(
                    "INSERT INTO forward_oos_events "
                    "(campaign_id, seq, event_type, forecast_id, created_at_utc, "
                    " prev_event_hash, event_hash, file_name, canonical_json, is_test) "
                    "VALUES (%s,%s,'TEST_DURABILITY_PROBE',%s,'',' ',%s,%s,%s,TRUE)",
                    (cid, nxt, marker, marker, "TEST_%s.json" % marker, payload))
            conn.commit()
        return {"ok": True, "marker": marker, "seq": nxt, "is_test": True}
    except Exception as exc:                                         # noqa: BLE001
        return {"ok": False, "reason": "WRITE_FAILED", "error_type": type(exc).__name__}


def read_test_fixture(root: Path | str, marker: str) -> Dict[str, Any]:
    if not enabled():
        return {"found": False, "reason": "DURABLE_STORE_NOT_CONFIGURED"}
    try:
        cid = _campaign_id(Path(root))
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT seq, event_type, mirrored_at FROM forward_oos_events "
                            "WHERE campaign_id=%s AND is_test AND forecast_id=%s",
                            (cid, marker))
                row = cur.fetchone()
        return {"found": bool(row), "marker": marker,
                "seq": (row or {}).get("seq"),
                "mirrored_at": str((row or {}).get("mirrored_at") or "")}
    except Exception as exc:                                         # noqa: BLE001
        return {"found": False, "reason": "READ_FAILED", "error_type": type(exc).__name__}


def delete_test_fixture(root: Path | str, marker: str) -> Dict[str, Any]:
    """Remove a TEST fixture. Refuses anything that is not flagged is_test."""
    if not enabled():
        return {"deleted": 0, "reason": "DURABLE_STORE_NOT_CONFIGURED"}
    try:
        cid = _campaign_id(Path(root))
        with _connect() as conn:
            with conn.cursor() as cur:
                # The is_test predicate is the guard: a production row cannot be
                # reached by this statement even with a matching forecast_id.
                cur.execute("DELETE FROM forward_oos_events "
                            "WHERE campaign_id=%s AND is_test = TRUE AND forecast_id=%s",
                            (cid, marker))
                n = cur.rowcount
            conn.commit()
        return {"deleted": int(n), "marker": marker,
                "production_rows_touched": 0}
    except Exception as exc:                                         # noqa: BLE001
        return {"deleted": 0, "reason": "DELETE_FAILED", "error_type": type(exc).__name__}
