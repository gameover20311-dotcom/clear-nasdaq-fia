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
Mirrors every appended event, its original evidence and its original head
anchor into Postgres in one transaction. Recovery restores only absent files
using the exact saved bytes, including partial losses after a redeploy.
An interrupted mirror of the current local tip can be retried while all its
original proofs still exist. Missing historical proofs are never synthesized.

WHAT IT DOES NOT DO
-------------------
* It does not become the source of truth. The file ledger and its hash chain
  remain authoritative; this is a durable copy of it.
* Application writes never update or delete a production row; the sole delete
  path refuses any row that is not explicitly flagged as a test fixture.
* It never backfills. Only events that the file layer actually appended are
  mirrored, with their original seq, timestamps and hashes.
* A mirror failure never fabricates success: durability_status() reports
  DEGRADED and names the failure so an operator can see that the event exists on
  ephemeral storage only.
"""
from __future__ import annotations

import json
import os
import fcntl
import hashlib
import re
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
_LEDGER_FILE_RE = re.compile(r"^\d{8}_[a-z0-9-]+_[A-Za-z0-9_-]+\.json$")
_EVIDENCE_FILE_RE = re.compile(r"^evidence/[A-Za-z0-9_-]+\.json$")
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
    # Existing event rows are never changed. Proofs have their own immutable
    # per-event bundle; the event and all its proofs commit in one transaction.
    """
    CREATE TABLE IF NOT EXISTS forward_oos_bundles (
        campaign_id TEXT NOT NULL,
        seq BIGINT NOT NULL,
        event_hash TEXT NOT NULL,
        head_json BYTEA NOT NULL,
        evidence_path TEXT,
        evidence_sha256 TEXT,
        evidence_json BYTEA,
        PRIMARY KEY (campaign_id, seq),
        FOREIGN KEY (campaign_id, seq)
            REFERENCES forward_oos_events(campaign_id, seq)
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
        cid = json.loads(seal.read_text(encoding="utf-8")).get("campaign_id")
        if not isinstance(cid, str) or not cid.strip() or cid == "UNKNOWN":
            raise ValueError("CAMPAIGN_ID_REQUIRED")
        return cid
    except Exception as exc:
        raise ValueError("CAMPAIGN_ID_REQUIRED") from exc


def _digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _safe_path(root: Path, relative: str, evidence: bool = False) -> Path:
    pattern = _EVIDENCE_FILE_RE if evidence else _LEDGER_FILE_RE
    if not pattern.fullmatch(relative):
        raise ValueError("INVALID_LEDGER_PATH")
    path = root / relative if evidence else root / "events" / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("UNSAFE_LEDGER_PATH")
    return path


def _check_head(blob: bytes, seq: int, event_hash: str) -> None:
    from fia.forward_oos import canonical_bytes
    head = json.loads(blob)
    unsigned = dict(head)
    claimed = unsigned.pop("anchor_hash", None)
    if (claimed != _digest(canonical_bytes(unsigned)) or
            head.get("events") != seq or head.get("head_event_hash") != event_hash):
        raise ValueError("HEAD_ANCHOR_MISMATCH")


def _local_bundle(root: Path, event: Dict[str, Any]) -> Dict[str, Any]:
    head_path = root / "LEDGER_HEAD.json"
    if head_path.is_symlink():
        raise ValueError("UNSAFE_HEAD_PATH")
    head = head_path.read_bytes()
    _check_head(head, event["seq"], event["event_hash"])
    meta = (event.get("payload") or {}).get("evidence") or {}
    bundle = {"seq": event["seq"], "event_hash": event["event_hash"],
              "head_json": head, "evidence_path": None,
              "evidence_sha256": None, "evidence_json": None}
    if meta:
        relative = str(meta.get("path") or "")
        blob = _safe_path(root, relative, evidence=True).read_bytes()
        if _digest(blob) != meta.get("sha256") or len(blob) != meta.get("bytes"):
            raise ValueError("EVIDENCE_MISMATCH")
        bundle.update(evidence_path=relative, evidence_sha256=meta["sha256"], evidence_json=blob)
    elif event.get("event_type") == "FORECAST_LOCK":
        raise ValueError("EVIDENCE_REFERENCE_MISSING")
    return bundle


def _archive(conn, cid: str):
    with conn.cursor() as cur:
        cur.execute("SELECT seq, file_name, canonical_json, event_hash FROM forward_oos_events "
                    "WHERE campaign_id=%s AND is_test = FALSE ORDER BY seq ASC", (cid,))
        rows = cur.fetchall() or []
        cur.execute("SELECT seq, event_hash, head_json, evidence_path, evidence_sha256, evidence_json "
                    "FROM forward_oos_bundles WHERE campaign_id=%s ORDER BY seq ASC", (cid,))
        bundles = {int(r["seq"]): r for r in (cur.fetchall() or [])}
    return rows, bundles


def _validate_archive(rows, bundles):
    """Validate stored proofs without constructing replacement evidence/anchors."""
    from fia.forward_oos import canonical_bytes
    result, issues, previous = [], [], "GENESIS"
    for expected, row in enumerate(rows, 1):
        try:
            event = json.loads(bytes(row["canonical_json"]))
            unsigned = dict(event)
            claimed = unsigned.pop("event_hash")
            name = "%08d_%s_%s.json" % (expected, event["event_type"].lower().replace("_", "-"), event["forecast_id"])
            if (event["seq"] != expected or row["seq"] != expected or
                    event["prev_event_hash"] != previous or claimed != row["event_hash"] or
                    claimed != _digest(canonical_bytes(unsigned)) or row["file_name"] != name or
                    not _LEDGER_FILE_RE.fullmatch(name)):
                raise ValueError("ARCHIVE_EVENT_MISMATCH")
        except Exception:
            # A broken chain is never installed as a recovery source.
            return [], ["invalid_saved_event:%s" % expected]
        previous = claimed
        item = {"row": row, "event": event, "head": None, "evidence": None}
        bundle = bundles.get(expected)
        if not bundle or bundle.get("event_hash") != claimed:
            issues.append("missing_saved_bundle:%s" % expected)
        else:
            try:
                head = bytes(bundle["head_json"])
                _check_head(head, expected, claimed)
                item["head"] = head
            except Exception:
                issues.append("invalid_saved_head:%s" % expected)
        meta = (event.get("payload") or {}).get("evidence") or {}
        if meta or event.get("event_type") == "FORECAST_LOCK":
            try:
                rel = str(meta.get("path") or "")
                blob = bytes((bundle or {}).get("evidence_json") or b"")
                if (not _EVIDENCE_FILE_RE.fullmatch(rel) or not blob or
                        (bundle or {}).get("evidence_path") != rel or
                        (bundle or {}).get("evidence_sha256") != meta.get("sha256") or
                        _digest(blob) != meta.get("sha256") or len(blob) != meta.get("bytes")):
                    raise ValueError("MISSING_OR_INVALID_EVIDENCE")
                item["evidence"] = (rel, blob)
            except Exception:
                issues.append("missing_or_invalid_saved_evidence:%s" % event["forecast_id"])
        result.append(item)
    return result, issues


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
            rows, bundles = _archive(conn, cid)
            archive, issues = _validate_archive(rows, bundles)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE is_test) AS t "
                    "FROM forward_oos_events WHERE campaign_id=%s", (cid,))
                row = cur.fetchone() or {}
        saved = {item["row"]["file_name"]: bytes(item["row"]["canonical_json"])
                 for item in archive}
        for path in (root / "events").glob("*.json"):
            if path.is_symlink() or saved.get(path.name) != path.read_bytes():
                issues.append("local_event_not_mirrored:%s" % path.name)
        complete = not issues
        return {"durable": complete, "backend": "postgres",
                "durability": "DURABLE" if complete else "DEGRADED",
                "survives_redeploy": complete, "campaign_id": cid,
                "mirrored_events": len(rows),
                "complete_bundles": sum(bool(item["head"]) and
                    (item["event"].get("event_type") != "FORECAST_LOCK" or bool(item["evidence"]))
                    for item in archive),
                "test_fixtures": int(row.get("t") or 0),
                "last_error": _LAST_ERROR,
                "issues": issues,
                "detail": ("events, original evidence and head anchors are recoverable from Postgres"
                           if complete else "event storage is incomplete; see missing or conflicting proofs")}
    except Exception as exc:                                         # noqa: BLE001
        # Never surface the driver message: it carries the DSN.
        return {"durable": False, "backend": "postgres", "durability": "DEGRADED",
                "survives_redeploy": False,
                "detail": "database unreachable (%s)" % type(exc).__name__}


def mirror_event(root: Path | str, event: Dict[str, Any], canonical: bytes,
                 file_name: str, is_test: bool = False) -> Dict[str, Any]:
    """Commit one event and its exact evidence/head bytes together, INSERT only."""
    global _LAST_ERROR
    if not enabled():
        return {"mirrored": False, "reason": "DURABLE_STORE_NOT_CONFIGURED"}
    try:
        from fia.forward_oos import canonical_bytes
        if is_test:
            raise ValueError("USE_ISOLATED_TEST_FIXTURE_WRITER")
        unsigned = dict(event)
        claimed = unsigned.pop("event_hash")
        if (json.loads(canonical) != event or _digest(canonical_bytes(unsigned)) != claimed or
                file_name != "%08d_%s_%s.json" % (
                    event["seq"], event["event_type"].lower().replace("_", "-"), event["forecast_id"])):
            raise ValueError("INVALID_MIRROR_EVENT")
        if _safe_path(Path(root), file_name).read_bytes() != canonical:
            raise ValueError("ORIGINAL_LOCAL_EVENT_REQUIRED")
        bundle = _local_bundle(Path(root), event)
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
                cur.execute("SELECT event_hash, file_name, canonical_json, is_test FROM forward_oos_events "
                            "WHERE campaign_id=%s AND seq=%s", (cid, event["seq"]))
                saved = cur.fetchone() or {}
                if (saved.get("event_hash") != claimed or saved.get("file_name") != file_name or
                        bytes(saved.get("canonical_json") or b"") != canonical or saved.get("is_test")):
                    raise ValueError("IMMUTABLE_EVENT_CONFLICT")
                cur.execute("INSERT INTO forward_oos_bundles "
                            "(campaign_id, seq, event_hash, head_json, evidence_path, evidence_sha256, evidence_json) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                            "ON CONFLICT (campaign_id, seq) DO NOTHING",
                            (cid, bundle["seq"], claimed, bundle["head_json"], bundle["evidence_path"],
                             bundle["evidence_sha256"], bundle["evidence_json"]))
                cur.execute("SELECT event_hash, head_json, evidence_path, evidence_sha256, evidence_json "
                            "FROM forward_oos_bundles WHERE campaign_id=%s AND seq=%s", (cid, event["seq"]))
                saved_bundle = cur.fetchone() or {}
                for key in ("event_hash", "head_json", "evidence_path", "evidence_sha256", "evidence_json"):
                    value = saved_bundle.get(key)
                    if key.endswith("json") and value is not None:
                        value = bytes(value)
                    if value != bundle[key]:
                        raise ValueError("IMMUTABLE_BUNDLE_CONFLICT")
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
    """Restore exact saved bytes, including partial losses; never invent proofs."""
    root = Path(root)
    if not enabled():
        return {"restored": 0, "reason": "DURABLE_STORE_NOT_CONFIGURED"}
    try:
        root.mkdir(parents=True, exist_ok=True)
        # Same mutex as append: restore cannot race an event/head update.
        with (root / ".ledger.lock").open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            with _connect() as conn:
                rows, bundles = _archive(conn, _campaign_id(root))
            archive, issues = _validate_archive(rows, bundles)
            # A failed mirror leaves the original local event/head intact. Only
            # that exact current tip can be retried: we never reconstruct an
            # earlier anchor from a later one or skip a gap in the DB chain.
            if _retry_local_tip(root, rows, bundles, archive):
                with _connect() as conn:
                    rows, bundles = _archive(conn, _campaign_id(root))
                archive, issues = _validate_archive(rows, bundles)
            written, evidence_written = 0, 0
            for item in archive:
                row = item["row"]
                path = _safe_path(root, row["file_name"])
                try:
                    written += _install_missing(path, bytes(row["canonical_json"]))
                    if item["evidence"]:
                        relative, blob = item["evidence"]
                        evidence_written += _install_missing(_safe_path(root, relative, evidence=True), blob)
                except ValueError:
                    issues.append("local_file_conflict:%s" % row["file_name"])
            if archive and archive[-1]["head"]:
                try:
                    _install_missing(root / "LEDGER_HEAD.json", archive[-1]["head"])
                except ValueError:
                    issues.append("local_file_conflict:LEDGER_HEAD.json")
            saved = {item["row"]["file_name"] for item in archive}
            for path in (root / "events").glob("*.json"):
                if path.name not in saved:
                    issues.append("local_event_not_mirrored:%s" % path.name)
            return {"ok": not issues, "restored": written, "evidence_restored": evidence_written,
                    "available": len(rows), "issues": issues}
    except Exception as exc:                                         # noqa: BLE001
        print("Forward-OOS durable restore FAILED -> %s" % type(exc).__name__)
        return {"ok": False, "restored": 0, "reason": "RESTORE_FAILED",
                "error_type": type(exc).__name__}


def _retry_local_tip(root: Path, rows, bundles, archive) -> bool:
    from fia.forward_oos import verify_ledger
    local = sorted((root / "events").glob("*.json"))
    count = len(local)
    if (not count or len(archive) != len(rows) or
            count not in (len(rows), len(rows) + 1) or
            (count == len(rows) and count in bundles)):
        return False
    for row in rows:
        path = _safe_path(root, row["file_name"])
        if not path.exists() or path.read_bytes() != bytes(row["canonical_json"]):
            return False
    if not verify_ledger(root, recover=False)["ok"]:
        return False
    blob = local[-1].read_bytes()
    return bool(mirror_event(root, json.loads(blob), blob, local[-1].name).get("mirrored"))


def _install_missing(path: Path, blob: bytes) -> int:
    if path.is_symlink():
        raise ValueError("LOCAL_FILE_CONFLICT")
    if path.exists():
        if path.read_bytes() != blob:
            raise ValueError("LOCAL_FILE_CONFLICT")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    with os.fdopen(fd, "wb") as handle:
        handle.write(blob)
        handle.flush()
        os.fsync(handle.fileno())
    return 1


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
