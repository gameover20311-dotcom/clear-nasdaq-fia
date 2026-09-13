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

import hashlib
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
_EVIDENCE_FILE_RE = __import__("re").compile(r"^evidence/[A-Za-z0-9._-]+\.json$")
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
    """
    CREATE TABLE IF NOT EXISTS forward_oos_evidence (
        campaign_id   TEXT NOT NULL,
        forecast_id   TEXT NOT NULL,
        file_name     TEXT NOT NULL,
        sha256        TEXT NOT NULL,
        canonical_json BYTEA NOT NULL,
        mirrored_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (campaign_id, forecast_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS forward_oos_ledger_heads (
        campaign_id    TEXT NOT NULL,
        events         BIGINT NOT NULL,
        head_event_hash TEXT NOT NULL,
        canonical_json BYTEA NOT NULL,
        mirrored_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (campaign_id, events)
    )
    """,
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
    """Report storage durability separately from scientific verification.

    DURABLE means bytes survive a redeploy. It is never a claim that the
    scientific record verifies. Evidence and ledger-head completeness are
    reported independently so a durable-but-incomplete mirror cannot be
    mistaken for verified Forward-OOS evidence.
    """
    root = Path(root)
    if not _database_url():
        return {"durable": False, "backend": "filesystem", "durability": "EPHEMERAL",
                "scope": "STORAGE_ONLY_NOT_SCIENTIFIC_VERIFICATION",
                "survives_redeploy": False,
                "scientific_artifacts_complete": False,
                "detail": "no DATABASE_URL; the ledger is destroyed by every redeploy"}
    if not _PG_AVAILABLE:
        return {"durable": False, "backend": "filesystem", "durability": "EPHEMERAL",
                "scope": "STORAGE_ONLY_NOT_SCIENTIFIC_VERIFICATION",
                "survives_redeploy": False,
                "scientific_artifacts_complete": False,
                "detail": "DATABASE_URL is set but the psycopg driver is not installed"}
    try:
        cid = _campaign_id(root)
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE is_test) AS t, "
                    "COUNT(*) FILTER (WHERE NOT is_test AND event_type='FORECAST_LOCK') AS locks "
                    "FROM forward_oos_events WHERE campaign_id=%s", (cid,))
                row = cur.fetchone() or {}
                cur.execute(
                    "SELECT COUNT(*) AS n FROM forward_oos_evidence WHERE campaign_id=%s", (cid,))
                evidence = cur.fetchone() or {}
                cur.execute(
                    "SELECT COUNT(*) AS missing FROM forward_oos_events e "
                    "LEFT JOIN forward_oos_evidence v ON v.campaign_id=e.campaign_id "
                    "AND v.forecast_id=e.forecast_id "
                    "WHERE e.campaign_id=%s AND e.is_test=FALSE "
                    "AND e.event_type='FORECAST_LOCK' AND v.forecast_id IS NULL", (cid,))
                missing_evidence = int((cur.fetchone() or {}).get("missing") or 0)
                cur.execute(
                    "SELECT seq, event_hash FROM forward_oos_events "
                    "WHERE campaign_id=%s AND is_test=FALSE ORDER BY seq DESC LIMIT 1", (cid,))
                last_event = cur.fetchone() or {}
                event_count = int(row.get("n") or 0) - int(row.get("t") or 0)
                head_complete = event_count == 0
                if event_count:
                    cur.execute(
                        "SELECT COUNT(*) AS n FROM forward_oos_ledger_heads "
                        "WHERE campaign_id=%s AND events=%s AND head_event_hash=%s",
                        (cid, event_count, str(last_event.get("event_hash") or "")))
                    head_complete = int((cur.fetchone() or {}).get("n") or 0) == 1
        complete = missing_evidence == 0 and head_complete
        missing = []
        if missing_evidence:
            missing.append("evidence:%d" % missing_evidence)
        if not head_complete:
            missing.append("ledger_head:1")
        return {"durable": True, "backend": "postgres", "durability": "DURABLE",
                "scope": "STORAGE_ONLY_NOT_SCIENTIFIC_VERIFICATION",
                "survives_redeploy": True, "campaign_id": cid,
                "mirrored_events": int(row.get("n") or 0),
                "production_events": event_count,
                "forecast_locks": int(row.get("locks") or 0),
                "mirrored_evidence": int(evidence.get("n") or 0),
                "ledger_head_complete": bool(head_complete),
                "scientific_artifacts_complete": bool(complete),
                "missing_scientific_artifacts": missing,
                "test_fixtures": int(row.get("t") or 0),
                "last_error": _LAST_ERROR,
                "detail": ("storage is durable; scientific verification is a separate gate")}
    except Exception as exc:                                         # noqa: BLE001
        return {"durable": False, "backend": "postgres", "durability": "DEGRADED",
                "scope": "STORAGE_ONLY_NOT_SCIENTIFIC_VERIFICATION",
                "survives_redeploy": False,
                "scientific_artifacts_complete": False,
                "detail": "database unreachable (%s)" % type(exc).__name__}


def _lock_evidence_payload(root: Path, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Load exact immutable evidence bytes referenced by a forecast lock."""
    if str(event.get("event_type") or "") != "FORECAST_LOCK":
        return None
    meta = ((event.get("payload") or {}).get("evidence") or {})
    rel = str(meta.get("path") or "")
    digest = str(meta.get("sha256") or "")
    if not rel or not digest or not _EVIDENCE_FILE_RE.match(rel):
        raise RuntimeError("FORECAST_LOCK_EVIDENCE_REFERENCE_INVALID")
    path = root / rel
    if not path.exists():
        raise RuntimeError("FORECAST_LOCK_EVIDENCE_FILE_MISSING")
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != digest:
        raise RuntimeError("FORECAST_LOCK_EVIDENCE_HASH_MISMATCH")
    return {"file_name": rel, "digest": digest, "blob": blob}


def _mirror_evidence_tx(cur: Any, campaign_id: str, event: Dict[str, Any],
                        evidence: Optional[Dict[str, Any]]) -> None:
    """Persist exact evidence bytes in the same transaction as the event/head."""
    if evidence is None:
        return
    forecast_id = str(event.get("forecast_id") or "")
    cur.execute(
        "INSERT INTO forward_oos_evidence "
        "(campaign_id, forecast_id, file_name, sha256, canonical_json) "
        "VALUES (%s,%s,%s,%s,%s) "
        "ON CONFLICT (campaign_id, forecast_id) DO NOTHING",
        (campaign_id, forecast_id, evidence["file_name"],
         evidence["digest"], evidence["blob"]))
    cur.execute(
        "SELECT file_name, sha256, canonical_json FROM forward_oos_evidence "
        "WHERE campaign_id=%s AND forecast_id=%s", (campaign_id, forecast_id))
    existing = cur.fetchone() or {}
    if (str(existing.get("file_name") or "") != evidence["file_name"]
            or str(existing.get("sha256") or "") != evidence["digest"]
            or bytes(existing.get("canonical_json") or b"") != evidence["blob"]):
        raise RuntimeError("EVIDENCE_MIRROR_CONFLICT")


def mirror_event(root: Path | str, event: Dict[str, Any], canonical: bytes,
                 file_name: str, is_test: bool = False) -> Dict[str, Any]:
    """Copy an event and its exact ledger-head anchor in one DB transaction."""
    global _LAST_ERROR
    if not enabled():
        return {"mirrored": False, "reason": "DURABLE_STORE_NOT_CONFIGURED"}
    try:
        root = Path(root)
        cid = _campaign_id(root)
        head_path = root / "LEDGER_HEAD.json"
        if not head_path.exists():
            raise RuntimeError("LEDGER_HEAD_MISSING_AT_MIRROR_TIME")
        head_blob = head_path.read_bytes()
        head_obj = json.loads(head_blob.decode("utf-8"))
        evidence = _lock_evidence_payload(root, event)
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
                # ON CONFLICT must never turn a different event at the same
                # scientific sequence into a false success. Re-read the row and
                # prove the durable bytes/identity are exactly the event being
                # mirrored before evidence/head writes may continue.
                cur.execute(
                    "SELECT event_type, forecast_id, created_at_utc, prev_event_hash, "
                    "event_hash, file_name, canonical_json, is_test "
                    "FROM forward_oos_events WHERE campaign_id=%s AND seq=%s",
                    (cid, int(event.get("seq") or 0)))
                existing_event = cur.fetchone() or {}
                expected_event = {
                    "event_type": str(event.get("event_type") or ""),
                    "forecast_id": str(event.get("forecast_id") or ""),
                    "created_at_utc": str(event.get("created_at_utc") or ""),
                    "prev_event_hash": str(event.get("prev_event_hash") or ""),
                    "event_hash": str(event.get("event_hash") or ""),
                    "file_name": str(file_name),
                    "canonical_json": bytes(canonical),
                    "is_test": bool(is_test),
                }
                observed_event = {
                    "event_type": str(existing_event.get("event_type") or ""),
                    "forecast_id": str(existing_event.get("forecast_id") or ""),
                    "created_at_utc": str(existing_event.get("created_at_utc") or ""),
                    "prev_event_hash": str(existing_event.get("prev_event_hash") or ""),
                    "event_hash": str(existing_event.get("event_hash") or ""),
                    "file_name": str(existing_event.get("file_name") or ""),
                    "canonical_json": bytes(existing_event.get("canonical_json") or b""),
                    "is_test": bool(existing_event.get("is_test")),
                }
                if observed_event != expected_event:
                    raise RuntimeError("EVENT_MIRROR_CONFLICT")
                _mirror_evidence_tx(cur, cid, event, evidence)
                if not is_test:
                    cur.execute(
                        "INSERT INTO forward_oos_ledger_heads "
                        "(campaign_id, events, head_event_hash, canonical_json) "
                        "VALUES (%s,%s,%s,%s) ON CONFLICT (campaign_id, events) DO NOTHING",
                        (cid, int(head_obj.get("events") or 0),
                         str(head_obj.get("head_event_hash") or ""), head_blob))
                    cur.execute(
                        "SELECT head_event_hash, canonical_json FROM forward_oos_ledger_heads "
                        "WHERE campaign_id=%s AND events=%s",
                        (cid, int(head_obj.get("events") or 0)))
                    existing = cur.fetchone() or {}
                    if (str(existing.get("head_event_hash") or "") != str(head_obj.get("head_event_hash") or "")
                            or bytes(existing.get("canonical_json") or b"") != head_blob):
                        raise RuntimeError("LEDGER_HEAD_MIRROR_CONFLICT")
            conn.commit()
        _LAST_ERROR = None
        return {"mirrored": True, "seq": event.get("seq"), "ledger_head_mirrored": not is_test}
    except Exception as exc:                                         # noqa: BLE001
        _LAST_ERROR = type(exc).__name__
        print("Forward-OOS durable mirror FAILED -> %s "
              "(event exists on ephemeral storage only)" % type(exc).__name__)
        return {"mirrored": False, "reason": "MIRROR_FAILED",
                "error_type": type(exc).__name__}


def mirror_evidence(root: Path | str, forecast_id: str, file_name: str,
                    digest: str, canonical: bytes) -> Dict[str, Any]:
    """Persist exact pre-move evidence bytes before the lock can be accepted."""
    global _LAST_ERROR
    if not enabled():
        return {"mirrored": False, "reason": "DURABLE_STORE_NOT_CONFIGURED"}
    if not _EVIDENCE_FILE_RE.match(str(file_name)):
        return {"mirrored": False, "reason": "INVALID_EVIDENCE_PATH"}
    try:
        cid = _campaign_id(Path(root))
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO forward_oos_evidence "
                    "(campaign_id, forecast_id, file_name, sha256, canonical_json) "
                    "VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT (campaign_id, forecast_id) DO NOTHING",
                    (cid, str(forecast_id), str(file_name), str(digest), canonical))
                cur.execute(
                    "SELECT file_name, sha256, canonical_json FROM forward_oos_evidence "
                    "WHERE campaign_id=%s AND forecast_id=%s", (cid, str(forecast_id)))
                existing = cur.fetchone() or {}
                if (str(existing.get("file_name") or "") != str(file_name)
                        or str(existing.get("sha256") or "") != str(digest)
                        or bytes(existing.get("canonical_json") or b"") != canonical):
                    raise RuntimeError("EVIDENCE_MIRROR_CONFLICT")
            conn.commit()
        _LAST_ERROR = None
        return {"mirrored": True, "forecast_id": str(forecast_id), "sha256": str(digest)}
    except Exception as exc:                                         # noqa: BLE001
        _LAST_ERROR = type(exc).__name__
        return {"mirrored": False, "reason": "EVIDENCE_MIRROR_FAILED",
                "error_type": type(exc).__name__}

def restore_missing(root: Path | str) -> Dict[str, Any]:
    """Restore only exact bytes that were previously mirrored.

    Missing old evidence/head artifacts are never synthesized. If the
    mirror does not contain them, the verifier remains failed/UNVERIFIED.
    """
    root = Path(root)
    if not enabled():
        return {"restored": 0, "reason": "DURABLE_STORE_NOT_CONFIGURED"}
    events_dir = root / "events"
    evidence_dir = root / "evidence"
    try:
        cid = _campaign_id(root)
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT seq, file_name, canonical_json, event_hash FROM forward_oos_events "
                    "WHERE campaign_id=%s AND is_test = FALSE ORDER BY seq ASC", (cid,))
                rows = cur.fetchall() or []
                cur.execute(
                    "SELECT forecast_id, file_name, sha256, canonical_json "
                    "FROM forward_oos_evidence WHERE campaign_id=%s", (cid,))
                evidence_rows = cur.fetchall() or []
                cur.execute(
                    "SELECT events, head_event_hash, canonical_json FROM forward_oos_ledger_heads "
                    "WHERE campaign_id=%s ORDER BY events DESC LIMIT 1", (cid,))
                head_row = cur.fetchone()
        events_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        event_written = 0
        evidence_written = 0
        head_written = 0
        for r in rows:
            name = str(r["file_name"])
            if not _LEDGER_FILE_RE.match(name):
                print("Forward-OOS restore skipped non-ledger row: %s" % name[:64])
                continue
            path = events_dir / name
            if path.exists():
                continue
            blob = bytes(r["canonical_json"])
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            with os.fdopen(fd, "wb") as f:
                f.write(blob); f.flush(); os.fsync(f.fileno())
            event_written += 1
        for r in evidence_rows:
            rel = str(r["file_name"])
            if not _EVIDENCE_FILE_RE.match(rel):
                print("Forward-OOS restore skipped invalid evidence path: %s" % rel[:64])
                continue
            path = root / rel
            if path.exists():
                continue
            blob = bytes(r["canonical_json"])
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            with os.fdopen(fd, "wb") as f:
                f.write(blob); f.flush(); os.fsync(f.fileno())
            evidence_written += 1
        head_path = root / "LEDGER_HEAD.json"
        if head_row and not head_path.exists():
            blob = bytes(head_row["canonical_json"])
            fd = os.open(head_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            with os.fdopen(fd, "wb") as f:
                f.write(blob); f.flush(); os.fsync(f.fileno())
            head_written = 1
        return {"restored": event_written + evidence_written + head_written,
                "events_restored": event_written,
                "evidence_restored": evidence_written,
                "ledger_head_restored": head_written,
                "available_events": len(rows),
                "available_evidence": len(evidence_rows),
                "head_available": bool(head_row)}
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
