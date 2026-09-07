"""SOL56 NEW FORWARD OOS PRE-MOVE VALIDATION.

This module is deliberately separate from historical backtests and the legacy
Phase-26 mutable CSV.  It creates a tamper-evident, append-only event ledger for
*new* market forecasts made before their outcomes exist.

Truth rules
-----------
- No historical import path exists.
- One daily checkpoint, America/New_York, default 13:00 ET.
- Missed checkpoints are never backfilled.
- Forecast/evidence files are created once and never edited by this module.
- 4H/8H outcomes are later appended as separate immutable resolution events.
- The entry-time explicit NQ futures contract is frozen and reused for outcomes.
- Only completed 5-minute bars at/before the requested timestamp are eligible.
- Missing/stale prices stay unresolved; no proxy/zero/current-price substitution.
- The legacy observed holdout is permanently ineligible for promotion.
- BASE_FIA remains production; candidate promotion needs genuinely new forward OOS.

Local files are tamper-*evident*, not magically tamper-proof against a filesystem
owner who deletes the whole directory.  Hash chaining, immutable-by-application
files, and evidence hashes make edits/deletions detectable in normal operation.
"""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import math
import re
import os
import statistics
from dataclasses import asdict, is_dataclass
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
SCHEMA_VERSION = "SOL56_FORWARD_OOS_V4_AUDITED"
PROGRAM_NAME = "CLEAR_NASDAQ_NEW_FORWARD_OOS_PREMOVE"
MODEL_NAME = "BASE_FIA"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "fia_forward_oos"
DEFAULT_CAMPAIGN_SEAL = ROOT / "fia_forward_oos" / "FORWARD_OOS_CAMPAIGN_SEAL.json"
EVENT_DIRNAME = "events"
EVIDENCE_DIRNAME = "evidence"
LOCK_FILENAME = ".ledger.lock"
HEAD_FILENAME = "LEDGER_HEAD.json"
MIN_REPORT_N = 30
TARGET_PROMOTION_N = 50

CORE_FINGERPRINT_FILES = (
    "fia/engine.py",
    "fia/providers.py",
    "fia/accuracy_engine.py",
    "fia/learning_engine.py",
    "fia/forward_oos.py",
    "main.py",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        return out if math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def _primitive(value: Any) -> Any:
    """Convert arbitrary provider/Pydantic values into deterministic JSON data."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return _primitive(value.model_dump())
    if is_dataclass(value):
        return _primitive(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _primitive(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (list, tuple, set)):
        return [_primitive(v) for v in value]
    if hasattr(value, "tolist"):
        try:
            return _primitive(value.tolist())
        except Exception:
            pass
    return str(value)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _primitive(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _production_fingerprint_files(
    backend_root: Path = ROOT,
) -> Tuple[str, ...]:
    """
    V2 seals the production FIA dependency surface instead of
    only a short hand-written subset.
    """
    rels = []

    fia_root = backend_root / "fia"

    if fia_root.exists():
        for path in sorted(fia_root.rglob("*.py")):
            name = path.name.lower()

            if name.startswith("test_"):
                continue
            if "backup" in name:
                continue
            if "before_" in name:
                continue
            if "(" in path.name or ")" in path.name:
                continue

            rels.append(
                str(path.relative_to(backend_root))
            )

    for rel in (
        "main.py",
        "run_forward_oos_daemon.py",
    ):
        if rel not in rels:
            rels.append(rel)

    return tuple(rels)


def model_fingerprint(
    backend_root: Path = ROOT,
) -> Dict[str, Any]:
    files: Dict[str, str] = {}

    for rel in _production_fingerprint_files(
        backend_root
    ):
        path = backend_root / rel
        files[rel] = (
            sha256_file(path)
            if path.exists()
            else "MISSING"
        )

    digest = sha256_bytes(
        canonical_bytes(files)
    )

    return {
        "algorithm": "sha256",
        "digest": digest,
        "files": files,
        "file_count": len(files),
    }


def build_campaign_seal(now: Optional[datetime] = None) -> Dict[str, Any]:
    now = (now or utcnow()).astimezone(timezone.utc)
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": "SOL56-NEW-FORWARD-OOS-V4-AUDITED",
        "sealed_at_utc": _iso(now),
        "production_model": MODEL_NAME,
        "model_fingerprint": model_fingerprint(),
        "shadow_candidate": None,
        "checkpoint_et": str(os.getenv("FIA_FORWARD_OOS_CHECKPOINT_ET", "13:00") or "13:00"),
        "grace_minutes": max(
            1,
            int(
                os.getenv(
                    "FIA_FORWARD_OOS_GRACE_MINUTES",
                    "10",
                )
                or "10"
            ),
        ),
        "require_explicit_contract": True,
        "minimum_interim_report_n": MIN_REPORT_N,
        "target_final_sample_n": TARGET_PROMOTION_N,
        "old_observed_holdout_eligible": False,
        "old_observed_holdout_untouched_rows": 0,
        "historical_tuning_after_seal_allowed": False,
        "missed_checkpoint_backfill_allowed": False,
        "forecast_edit_or_delete_allowed": False,
        "automatic_model_promotion": False,
    }
    return {**unsigned, "seal_hash": sha256_bytes(canonical_bytes(unsigned))}


def write_campaign_seal(path: Path | str = DEFAULT_CAMPAIGN_SEAL, now: Optional[datetime] = None, overwrite: bool = False) -> Dict[str, Any]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return verify_campaign_seal(path)
    payload = build_campaign_seal(now)
    data = canonical_bytes(payload) + b"\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        tmp.chmod(0o444)
    except OSError:
        pass
    os.replace(tmp, path)
    try:
        path.chmod(0o444)
    except OSError:
        pass
    return verify_campaign_seal(path)


def verify_campaign_seal(path: Path | str = DEFAULT_CAMPAIGN_SEAL) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {"ok": False, "reason": "CAMPAIGN_SEAL_MISSING", "path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        unsigned = dict(payload)
        claimed = str(unsigned.pop("seal_hash", ""))
        computed = sha256_bytes(canonical_bytes(unsigned))
        current = model_fingerprint()
        sealed = payload.get("model_fingerprint") or {}
        fingerprint_match = sealed.get("digest") == current.get("digest")
        return {
            "ok": claimed == computed and fingerprint_match,
            "seal_hash_valid": claimed == computed,
            "model_fingerprint_match": fingerprint_match,
            "path": str(path),
            "campaign_id": payload.get("campaign_id"),
            "sealed_at_utc": payload.get("sealed_at_utc"),
            "sealed_model_fingerprint": sealed,
            "current_model_fingerprint": current,
            "policy": {k: payload.get(k) for k in (
                "shadow_candidate", "old_observed_holdout_eligible",
                "old_observed_holdout_untouched_rows",
                "historical_tuning_after_seal_allowed",
                "missed_checkpoint_backfill_allowed",
                "forecast_edit_or_delete_allowed", "automatic_model_promotion",
            )},
        }
    except Exception as exc:
        return {"ok": False, "reason": f"CAMPAIGN_SEAL_UNREADABLE:{exc}", "path": str(path)}


def _checkpoint_time() -> dtime:
    raw = str(os.getenv("FIA_FORWARD_OOS_CHECKPOINT_ET", "13:00") or "13:00").strip()
    try:
        hh, mm = raw.split(":", 1)
        return dtime(hour=int(hh), minute=int(mm))
    except Exception as exc:
        raise ValueError("FIA_FORWARD_OOS_CHECKPOINT_ET must be HH:MM") from exc


def checkpoint_state(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Return whether a *new* live lock is permitted right now.

    There is intentionally no backfill mode.  A process started after the grace
    window must wait for the next eligible trading weekday.
    """
    now = (now or utcnow()).astimezone(timezone.utc)
    ny = now.astimezone(NY)
    cp = _checkpoint_time()
    grace = max(1, int(os.getenv("FIA_FORWARD_OOS_GRACE_MINUTES", "10") or "10"))
    scheduled_ny = datetime.combine(ny.date(), cp, tzinfo=NY)
    closes_ny = scheduled_ny + timedelta(minutes=grace)
    weekday = ny.weekday() < 5
    eligible = weekday and scheduled_ny <= ny < closes_ny
    return {
        "eligible_now": eligible,
        "weekday": weekday,
        "now_utc": _iso(now),
        "now_et": ny.isoformat(),
        "checkpoint_date_et": ny.date().isoformat(),
        "scheduled_checkpoint_et": scheduled_ny.isoformat(),
        "window_closes_et": closes_ny.isoformat(),
        "grace_minutes": grace,
        "missed_backfill_allowed": False,
    }


def _dirs(root: Path) -> Tuple[Path, Path]:
    events = root / EVENT_DIRNAME
    evidence = root / EVIDENCE_DIRNAME
    events.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    return events, evidence


def _event_files(root: Path) -> List[Path]:
    events, _ = _dirs(root)
    return sorted(events.glob("*.json"))


def _read_event(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError(f"Invalid event object: {path}")
    return value


def _head_payload(events: int, head_event_hash: str, updated_at: datetime) -> Dict[str, Any]:
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "events": int(events),
        "head_event_hash": str(head_event_hash),
        "updated_at_utc": _iso(updated_at),
    }
    return {**unsigned, "anchor_hash": sha256_bytes(canonical_bytes(unsigned))}


def _write_head(root: Path, events: int, head_event_hash: str, now: datetime) -> None:
    path = root / HEAD_FILENAME
    tmp = root / (HEAD_FILENAME + ".tmp")
    payload = _head_payload(events, head_event_hash, now)
    root.mkdir(parents=True, exist_ok=True)
    with tmp.open("wb") as f:
        f.write(canonical_bytes(payload) + b"\n")
        f.flush()
        os.fsync(f.fileno())
    try:
        tmp.chmod(0o444)
    except OSError:
        pass
    os.replace(tmp, path)
    try:
        path.chmod(0o444)
    except OSError:
        pass


def _restore_from_durable_if_empty(root: Path) -> None:
    """If local storage came back empty after a redeploy, rebuild from Postgres.

    Only ever writes files that are absent, so a live ledger cannot be clobbered.
    """
    try:
        events_dir = root / "events"
        if events_dir.exists() and any(events_dir.glob("*.json")):
            return
        from fia.forward_oos_durable import enabled as _durable_enabled, restore_missing
        if not _durable_enabled():
            return
        result = restore_missing(root)
        if result.get("restored"):
            print("Forward-OOS ledger restored from durable store: %s event(s)"
                  % result["restored"])
    except Exception as exc:                                         # noqa: BLE001
        print("Forward-OOS durable restore skipped -> %s" % type(exc).__name__)


def verify_ledger(root: Path | str = DEFAULT_ROOT) -> Dict[str, Any]:
    root = Path(root)
    _restore_from_durable_if_empty(root)
    files = _event_files(root)
    prev = "GENESIS"
    expected_seq = 1
    issues: List[str] = []
    event_hashes: List[str] = []
    forecast_ids: set[str] = set()
    lock_events = 0
    resolution_events = 0

    for path in files:
        try:
            event = _read_event(path)
        except Exception as exc:
            issues.append(f"unreadable_event:{path.name}:{exc}")
            continue
        seq = event.get("seq")
        if seq != expected_seq:
            issues.append(f"sequence:{path.name}:expected={expected_seq}:got={seq}")
        if event.get("prev_event_hash") != prev:
            issues.append(f"chain_prev:{path.name}")
        claimed = str(event.get("event_hash") or "")
        unsigned = dict(event)
        unsigned.pop("event_hash", None)
        computed = sha256_bytes(canonical_bytes(unsigned))
        if claimed != computed:
            issues.append(f"event_hash:{path.name}")
        if path.name[:8].isdigit() and int(path.name[:8]) != seq:
            issues.append(f"filename_sequence:{path.name}")

        et = str(event.get("event_type") or "")
        fid = str(event.get("forecast_id") or "")
        if et == "FORECAST_LOCK":
            lock_events += 1
            if fid in forecast_ids:
                issues.append(f"duplicate_forecast_lock:{fid}")
            forecast_ids.add(fid)
            evidence_meta = event.get("payload", {}).get("evidence", {})
            rel = evidence_meta.get("path")
            digest = evidence_meta.get("sha256")
            if not rel or not digest:
                issues.append(f"missing_evidence_ref:{fid}")
            else:
                ep = root / rel
                if not ep.exists():
                    issues.append(f"missing_evidence_file:{fid}")
                elif sha256_file(ep) != digest:
                    issues.append(f"evidence_hash:{fid}")
        elif et in {"RESOLUTION_4H", "RESOLUTION_8H"}:
            resolution_events += 1
            if fid not in forecast_ids:
                issues.append(f"resolution_without_prior_lock:{fid}")

        event_hashes.append(claimed)
        prev = claimed
        expected_seq += 1

    head_path = root / HEAD_FILENAME
    if files:
        if not head_path.exists():
            issues.append("missing_ledger_head_anchor")
        else:
            try:
                head = json.loads(head_path.read_text(encoding="utf-8"))
                unsigned_head = dict(head)
                claimed_anchor = str(unsigned_head.pop("anchor_hash", ""))
                if claimed_anchor != sha256_bytes(canonical_bytes(unsigned_head)):
                    issues.append("ledger_head_anchor_hash")
                if int(head.get("events", -1)) != len(files):
                    issues.append(f"ledger_head_event_count:expected={len(files)}:got={head.get('events')}")
                if str(head.get("head_event_hash") or "") != prev:
                    issues.append("ledger_head_event_hash")
            except Exception as exc:
                issues.append(f"unreadable_ledger_head:{exc}")
    elif head_path.exists():
        try:
            head = json.loads(head_path.read_text(encoding="utf-8"))
            if int(head.get("events", -1)) != 0:
                issues.append("orphan_nonempty_ledger_head")
        except Exception as exc:
            issues.append(f"unreadable_ledger_head:{exc}")

    return {
        "ok": not issues,
        "schema_version": SCHEMA_VERSION,
        "events": len(files),
        "forecast_locks": lock_events,
        "resolution_events": resolution_events,
        "head_event_hash": prev,
        "issues": issues,
        # V6.6.2: this was a hardcoded True and therefore reported "tamper_evident"
        # even while listing integrity issues. It now reflects the actual audit.
        "tamper_evident": not issues,
        "tamper_proof_against_filesystem_owner": False,
    }


def _append_event(root: Path, event_type: str, forecast_id: str, payload: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    events, _ = _dirs(root)
    lock_path = root / LOCK_FILENAME
    root.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            audit = verify_ledger(root)
            if not audit["ok"]:
                raise RuntimeError("Forward OOS ledger integrity failure; refusing append: " + ";".join(audit["issues"]))
            # Cross-process idempotency: duplicate locks/resolutions are rejected
            # while holding the filesystem lock, not only by a pre-check outside it.
            for existing_path in _event_files(root):
                existing = _read_event(existing_path)
                if existing.get("event_type") == event_type and existing.get("forecast_id") == forecast_id:
                    raise FileExistsError(f"Immutable event already exists: {event_type}:{forecast_id}")
            seq = audit["events"] + 1
            unsigned = {
                "schema_version": SCHEMA_VERSION,
                "seq": seq,
                "event_type": event_type,
                "forecast_id": forecast_id,
                "created_at_utc": _iso(now),
                "prev_event_hash": audit["head_event_hash"],
                "payload": _primitive(payload),
            }
            event = dict(unsigned)
            event["event_hash"] = sha256_bytes(canonical_bytes(unsigned))
            safe_type = event_type.lower().replace("_", "-")
            path = events / f"{seq:08d}_{safe_type}_{forecast_id}.json"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(canonical_bytes(event))
                    f.write(b"\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                try:
                    path.unlink(missing_ok=True)
                finally:
                    raise
            try:
                path.chmod(0o444)
            except OSError:
                pass
            _write_head(root, seq, event["event_hash"], now)
            # V6.6.8 DURABLE MIRROR.
            # The file above lives on ephemeral deploy storage. Observed on
            # 2026-09-07: a real abstention observation was written, then erased
            # by the next deploy. The event is copied to Postgres byte-for-byte
            # so it can be restored. This never alters the event, the chain or
            # the file; a mirror failure is loud and leaves the file intact.
            try:
                from fia.forward_oos_durable import mirror_event as _mirror
                _mirror(root, event, canonical_bytes(event) + b"\n", path.name)
            except Exception as _exc:                                # noqa: BLE001
                print("Forward-OOS durable mirror unavailable -> %s"
                      % type(_exc).__name__)
            return event
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _write_evidence_once(root: Path, forecast_id: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    _, evidence_dir = _dirs(root)
    rel = Path(EVIDENCE_DIRNAME) / f"{forecast_id}.json"
    path = root / rel
    data = canonical_bytes(evidence) + b"\n"
    digest = sha256_bytes(data)
    if path.exists():
        existing = sha256_file(path)
        if existing != digest:
            raise RuntimeError(f"Evidence file already exists with different content: {forecast_id}")
        return {"path": str(rel), "sha256": existing, "bytes": path.stat().st_size}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    try:
        path.chmod(0o444)
    except OSError:
        pass
    return {"path": str(rel), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def _locks(root: Path) -> List[Dict[str, Any]]:
    return [e for e in (_read_event(p) for p in _event_files(root)) if e.get("event_type") == "FORECAST_LOCK"]


def _has_lock_for_date(root: Path, checkpoint_date_et: str) -> Optional[Dict[str, Any]]:
    for event in _locks(root):
        if event.get("payload", {}).get("checkpoint_date_et") == checkpoint_date_et:
            return event
    return None


def _forecast_values(forecast: Any, premove: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = _primitive(forecast)
    if not isinstance(data, dict):
        raise ValueError("Forecast is not serializable as an object")
    bull = _float(data.get("bullish_probability"))
    bear = _float(data.get("bearish_probability"))
    confidence = _float(data.get("confidence"))
    direction = str(data.get("direction") or "").upper()
    if direction not in {"BULLISH", "BEARISH"}:
        raise ValueError("Forward OOS requires a binary BASE_FIA direction")
    if bull is None or bear is None or not (0 <= bull <= 100 and 0 <= bear <= 100):
        raise ValueError("Invalid forecast probabilities")
    if abs((bull + bear) - 100.0) > 0.2:
        raise ValueError("Bullish/bearish probabilities do not sum to 100")
    if confidence is None or not 0 <= confidence <= 100:
        raise ValueError("Invalid confidence")
    # DISPLAY/LOCK PARITY. The trader-facing 4H and 8H distributions come from
    # the PRE-MOVE WATCH layer, which computes each horizon separately with its
    # own weights and its own calibrator. Previously this function wrote the base
    # engine's single distribution into BOTH horizon slots, so the ledger locked
    # a different number from the one displayed. When the pre-move view is
    # supplied we lock exactly what was shown, per horizon, and record the
    # pre-move forecast id + evidence hash so parity is independently verifiable.
    horizon_probabilities: Dict[str, Any] = {}
    premove_meta: Dict[str, Any] = {}
    pm_h = ((premove or {}).get("horizons") or {}) if isinstance(premove, dict) else {}
    for _h in ("4h", "8h"):
        cell = pm_h.get(_h) if isinstance(pm_h.get(_h), dict) else None
        pb = _float((cell or {}).get("bullish_probability"))
        pr = _float((cell or {}).get("bearish_probability"))
        if cell is not None and pb is not None and pr is not None:
            horizon_probabilities[_h] = {
                "bullish_probability": round(pb, 6),
                "bearish_probability": round(pr, 6),
                "direction": str(cell.get("direction") or "").upper(),
                "state": str(cell.get("state") or "").upper(),
                "confidence": _float(cell.get("confidence")),
                "raw_probability": _float(cell.get("raw_probability")),
                "calibrated_bullish_probability": _float(cell.get("calibrated_bullish_probability")),
                "actionable": bool(cell.get("actionable")),
                "source": "PREMOVE_WATCH_PER_HORIZON_AS_DISPLAYED",
            }
        else:
            # No pre-move view available: fall back to the base distribution and
            # say so explicitly rather than implying a per-horizon estimate.
            horizon_probabilities[_h] = {
                "bullish_probability": round(bull, 6),
                "bearish_probability": round(bear, 6),
                "source": "BASE_FIA_SHARED_PREMOVE_DISTRIBUTION",
            }
    if isinstance(premove, dict):
        premove_meta = {
            "forecast_id": premove.get("forecast_id"),
            "evidence_hash": premove.get("evidence_hash"),
            "state": str(premove.get("state") or "").upper(),
            "schema_version": premove.get("schema_version"),
        }

    return {
        "model_name": MODEL_NAME,
        "direction": direction,
        "bullish_probability": round(bull, 6),
        "bearish_probability": round(bear, 6),
        "horizon_probabilities": horizon_probabilities,
        "premove": premove_meta,
        "confidence": round(confidence, 6),
        "regime": str(data.get("regime") or "UNKNOWN").upper(),
        "score": data.get("score"),
        "status": data.get("status"),
        "data_coverage": data.get("data_coverage"),
        "intelligence_coverage": data.get("intelligence_coverage"),
        "generated_at": data.get("generated_at"),
        "source_status": data.get("source_status") or {},
        "signals": data.get("signals") or [],
        "invalidation": data.get("invalidation") or [],
    }


def _extract_contract(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    raw = snapshot.get("data", {}) if isinstance(snapshot, dict) else {}
    liq = raw.get("nq_liquidity") or {}
    contract = str(liq.get("symbol") or "").strip().upper()
    quality = str(liq.get("source_quality") or "").strip().upper()
    source = str(liq.get("source") or "")
    explicit = quality == "EXPLICIT_CONTRACT" and contract.startswith("NQ") and contract != "NQ=F"
    return {"contract": contract or None, "source_quality": quality or None, "source": source, "explicit": explicit}


def _completed_close_from_start_bars(
    timestamps: Sequence[Any],
    closes: Sequence[Any],
    as_of: datetime,
    max_age_minutes: float,
    *,
    interval_minutes: int = 5,
    source: str,
) -> Optional[Dict[str, Any]]:
    """
    Select the newest fully completed bar.

    Both Massive Futures ``window_start`` and Yahoo chart timestamps
    represent bar START times. A 5-minute bar is eligible only when:

        bar_start + 5 minutes <= as_of

    Irregular timestamps (for example a live partial quote stamped
    03:40:37) are rejected. This prevents an unfinished candle from
    entering the scientific Forward-OOS record.
    """

    as_of = as_of.astimezone(timezone.utc)
    interval_seconds = int(interval_minutes * 60)

    best = None

    for raw_ts, raw_close in zip(
        timestamps or [],
        closes or [],
    ):
        try:
            ts = int(raw_ts)
            close = float(raw_close)

            if not math.isfinite(close):
                continue

            # Scientific rule: canonical completed 5m grid only.
            if ts % interval_seconds != 0:
                continue

            bar_start = datetime.fromtimestamp(
                ts,
                tz=timezone.utc,
            )

            bar_end = bar_start + timedelta(
                seconds=interval_seconds
            )

            if bar_end > as_of:
                continue

            if best is None or bar_start > best[0]:
                best = (
                    bar_start,
                    bar_end,
                    close,
                )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            continue

    if best is None:
        return None

    bar_start, bar_end, close = best

    age_min = (
        as_of - bar_end
    ).total_seconds() / 60.0

    if (
        age_min < -1e-9
        or age_min > max_age_minutes
    ):
        return None

    return {
        "bar_start_utc": _iso(bar_start),
        "bar_end_utc": _iso(bar_end),
        "close": round(close, 6),
        "age_minutes": round(age_min, 3),
        "source": source,
        "completed_bar": True,
        "interval_minutes": interval_minutes,
    }


def _completed_close_from_polygon_payload(
    payload: Any,
    as_of: datetime,
    max_age_minutes: float,
) -> Optional[Dict[str, Any]]:
    """
    Compatibility name retained.

    ProviderHub now normalizes Massive Futures v1 ``window_start``
    nanoseconds into Unix START seconds.
    """

    if not isinstance(payload, dict):
        return None

    return _completed_close_from_start_bars(
        payload.get("t") or [],
        payload.get("c") or [],
        as_of,
        max_age_minutes,
        interval_minutes=5,
        source=str(
            payload.get("provider")
            or "MASSIVE_FUTURES_V1"
        ),
    )


def _yahoo_explicit_symbol(
    contract: str,
    as_of: datetime,
) -> Optional[str]:
    """
    Convert an explicit FIA contract such as NQU6 to Yahoo's exact
    quarterly symbol NQU26.CME.

    No NQ=F continuous proxy is permitted.
    """

    contract = str(contract or "").strip().upper()

    if (
        len(contract) < 4
        or not contract.startswith("NQ")
        or contract == "NQ=F"
    ):
        return None

    month_code = contract[2]
    token = contract[3:]

    if month_code not in {"H", "M", "U", "Z"}:
        return None

    if not token.isdigit():
        return None

    ref_year = as_of.astimezone(
        timezone.utc
    ).year

    if len(token) == 1:
        digit = int(token)
        decade = (ref_year // 10) * 10

        candidates = (
            decade - 10 + digit,
            decade + digit,
            decade + 10 + digit,
        )

        year = min(
            candidates,
            key=lambda y: abs(y - ref_year),
        )

    elif len(token) == 2:
        year = 2000 + int(token)

    else:
        return None

    return (
        f"NQ{month_code}"
        f"{year % 100:02d}.CME"
    )


async def _yahoo_explicit_completed_close(
    hub: Any,
    contract: str,
    as_of: datetime,
    max_age_minutes: float,
) -> Optional[Dict[str, Any]]:
    """
    Fresh zero-cost fallback using the SAME quarterly NQ contract.

    Example:
        FIA contract:   NQU6
        Yahoo contract: NQU26.CME

    This is not NQ=F and does not change the frozen instrument.
    """

    yahoo_symbol = _yahoo_explicit_symbol(
        contract,
        as_of,
    )

    if not yahoo_symbol:
        return None

    period1 = int(
        (
            as_of
            - timedelta(hours=2)
        ).timestamp()
    )

    # Include a small amount after the target so Yahoo can return
    # the bar whose START is just before ``as_of``.
    period2 = int(
        (
            as_of
            + timedelta(minutes=10)
        ).timestamp()
    )

    try:
        payload = await hub.get(
            "https://"
            + "query1.finance.yahoo.com"
            + "/v8/finance/chart/"
            + yahoo_symbol,
            {
                "period1": period1,
                "period2": period2,
                "interval": "5m",
                "includePrePost": "true",
                "events": "history",
            },
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
        )
    except Exception:
        return None

    try:
        result = (
            ((payload or {}).get("chart") or {})
            .get("result")
            or []
        )

        if not result:
            return None

        result = result[0]

        timestamps = (
            result.get("timestamp")
            or []
        )

        quote = (
            (
                (
                    result.get("indicators")
                    or {}
                ).get("quote")
                or [{}]
            )[0]
        )

        closes = quote.get("close") or []

        out = _completed_close_from_start_bars(
            timestamps,
            closes,
            as_of,
            max_age_minutes,
            interval_minutes=5,
            source=(
                "YAHOO_EXPLICIT_CONTRACT_5M:"
                + yahoo_symbol
            ),
        )

        if out:
            out["contract"] = contract
            out["vendor_symbol"] = yahoo_symbol

        return out

    except Exception:
        return None


async def explicit_contract_completed_close(
    hub: Any,
    contract: str,
    as_of: datetime,
    max_age_minutes: float = 15.0,
) -> Optional[Dict[str, Any]]:
    """
    Obtain a fresh completed close for the frozen explicit contract.

    Priority:
      1. Massive Futures v1 explicit contract.
      2. Yahoo exact SAME quarterly CME contract.

    Continuous NQ=F is never used.
    """

    contract = str(
        contract or ""
    ).strip().upper()

    if (
        not contract.startswith("NQ")
        or contract == "NQ=F"
    ):
        return None

    start = as_of - timedelta(hours=2)

    # ---------------------------------------------------------
    # PRIMARY: Massive explicit futures contract
    # ---------------------------------------------------------

    try:
        payload = await hub.polygon_futures_candles(
            contract,
            multiplier=5,
            timespan="minute",
            start_ts=int(start.timestamp()),
            end_ts=int(as_of.timestamp()),
        )

        result = (
            _completed_close_from_polygon_payload(
                payload,
                as_of,
                max_age_minutes,
            )
        )

        if result is not None:
            result["contract"] = contract
            return result

    except Exception:
        pass

    # ---------------------------------------------------------
    # FRESH FALLBACK: Yahoo exact SAME CME quarterly contract
    # ---------------------------------------------------------

    return await _yahoo_explicit_completed_close(
        hub,
        contract,
        as_of,
        max_age_minutes,
    )


async def lock_abstention_observation(
    forecast: Any,
    snapshot: Dict[str, Any],
    premove: Dict[str, Any],
    root: Path | str = DEFAULT_ROOT,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Record a legitimate NO_EDGE as an immutable NON-DIRECTIONAL observation.

    WHY THIS EXISTS
    ---------------
    Abstention was previously invisible: `lock_live_forecast` refuses to lock a
    NO_EDGE (correctly -- an abstention is not a directional out-of-sample
    observation), and nothing else recorded it. The campaign therefore could not
    answer basic questions about its own behaviour: how often does it abstain?
    Is the conviction threshold too strict? Does abstaining actually improve the
    quality of the directional sample it keeps?

    WHAT THIS IS NOT
    ----------------
    This record is NEVER scored as BULLISH, BEARISH, 50/50, WIN or LOSS. It
    carries `directional: false` and `scoreable_as_directional: false`, is
    written under a distinct ABSTENTION_OBSERVATION event type, and is excluded
    from every directional statistic. Directional and abstention statistics stay
    strictly separate.

    The raw and published probabilities ARE preserved, because the honest record
    of an abstention is "the estimate was 50.02% with 0.14% confidence and we
    declined to call it", not "the estimate was 50/50".

    Same integrity rules as a directional lock: append-only, hash-chained, one
    per checkpoint date, no backfill, refuses outside the live window.
    """
    root = Path(root)
    now = (now or utcnow()).astimezone(timezone.utc)
    state = checkpoint_state(now)
    if not state["eligible_now"]:
        return {"ok": True, "created": False,
                "reason": "OUTSIDE_LIVE_CHECKPOINT_NO_BACKFILL", "checkpoint": state}

    existing = _has_abstention_for_date(root, state["checkpoint_date_et"])
    if existing:
        return {"ok": True, "created": False,
                "reason": "CHECKPOINT_ABSTENTION_ALREADY_RECORDED",
                "forecast_id": existing.get("forecast_id")}

    seal = verify_campaign_seal()
    if not seal.get("ok"):
        return {"ok": False, "created": False,
                "reason": "CAMPAIGN_SEAL_OR_MODEL_FINGERPRINT_INVALID", "seal": seal}

    pm = premove if isinstance(premove, dict) else {}
    horizons = pm.get("horizons") or {}
    quality = pm.get("evidence_quality") or {}
    data = snapshot.get("data") if isinstance(snapshot, dict) and isinstance(snapshot.get("data"), dict) else (snapshot or {})

    per_horizon: Dict[str, Any] = {}
    for h in ("4h", "8h"):
        cell = horizons.get(h) if isinstance(horizons.get(h), dict) else {}
        gate = cell.get("conviction_gate") or {}
        per_horizon[h] = {
            "state": str(cell.get("state") or "").upper(),
            "direction": str(cell.get("direction") or "").upper(),
            "actionable": bool(cell.get("actionable")),
            # Estimates preserved for transparency -- never rewritten to 50/50.
            "raw_probability": _float(cell.get("raw_probability")),
            "published_bullish_probability": _float(cell.get("bullish_probability")),
            "published_bearish_probability": _float(cell.get("bearish_probability")),
            "calibrated_bullish_probability": _float(cell.get("calibrated_bullish_probability")),
            "confidence": _float(cell.get("confidence")),
            "edge_points": _float(cell.get("edge_points")),
            "no_edge_reasons": list(gate.get("reasons") or []),
            "gate_thresholds": {"min_edge_points": gate.get("min_edge_points"),
                                "min_confidence": gate.get("min_confidence")},
            "evidence_direction": str(cell.get("evidence_direction") or "").upper(),
            "confidence_basis": cell.get("confidence_basis"),
        }

    cognitive = (snapshot or {}).get("cognitive") if isinstance(snapshot, dict) else None
    critic = (cognitive or {}).get("critic") if isinstance(cognitive, dict) else None
    hypotheses = (cognitive or {}).get("hypotheses") if isinstance(cognitive, dict) else None

    forecast_id = "abst-%s" % (str(pm.get("evidence_hash") or "")[:24]
                               or sha256_bytes(canonical_bytes(per_horizon))[:24])
    payload = {
        "schema": "CLEAR_NASDAQ_FORWARD_OOS_ABSTENTION_V1",
        "observation_type": "ABSTENTION",
        "directional": False,
        "scoreable_as_directional": False,
        "excluded_from_directional_statistics": True,
        "model_name": MODEL_NAME,
        "forecast_id": forecast_id,
        "premove_forecast_id": pm.get("forecast_id"),
        "evidence_hash": pm.get("evidence_hash"),
        "overall_state": str(pm.get("state") or "").upper(),
        "regime": pm.get("regime"),
        "observed_at_utc": pm.get("market_observation_utc"),
        "recorded_at_utc": _iso(now),
        "checkpoint_date_et": state["checkpoint_date_et"],
        "scheduled_checkpoint_et": state["scheduled_checkpoint_et"],
        "horizons": per_horizon,
        "evidence_quality": {
            "coverage": quality.get("coverage"),
            "grade": quality.get("grade"),
            "live_signal_count": quality.get("live_signal_count"),
            "total_signal_count": quality.get("total_signal_count"),
            "degraded": quality.get("degraded"),
            "stale": quality.get("stale"),
            "age_excluded_signals": quality.get("age_excluded_signals"),
            "market_session": quality.get("market_session"),
        },
        "data_quality": {
            "provider_health": (data or {}).get("provider_health"),
            "source_health": (data or {}).get("source_health"),
        },
        "three_brain_conflict": {
            "critic_severity": (critic or {}).get("severity"),
            "critic_objections": list((critic or {}).get("objections") or []),
            "bull_strength": ((hypotheses or {}).get("bullish_hypothesis") or {}).get("strength"),
            "bear_strength": ((hypotheses or {}).get("bearish_hypothesis") or {}).get("strength"),
            "available": bool(cognitive),
        },
        "campaign": {
            "campaign_id": seal.get("campaign_id"),
            "sealed_at_utc": seal.get("sealed_at_utc"),
            "model_fingerprint_digest": seal.get("sealed_model_fingerprint", {}).get("digest"),
        },
        "eligibility": {
            "genuinely_new_forward": True,
            "legacy_holdout_reused": False,
            "historical_backfill": False,
        },
        "note": ("Abstention record. NOT a directional forecast and NOT scoreable as a "
                 "win or loss. Probabilities are preserved for transparency, not as a call."),
    }
    try:
        event = _append_event(root, "ABSTENTION_OBSERVATION", forecast_id, payload, now)
    except FileExistsError:
        return {"ok": True, "created": False,
                "reason": "CHECKPOINT_ABSTENTION_ALREADY_RECORDED", "forecast_id": forecast_id}
    return {"ok": True, "created": True, "observation_type": "ABSTENTION",
            "forecast_id": forecast_id, "event_hash": event["event_hash"]}


def _has_abstention_for_date(root: Path, checkpoint_date_et: str) -> Optional[Dict[str, Any]]:
    for p in _event_files(root):
        e = _read_event(p)
        if not isinstance(e, dict):
            continue
        if e.get("event_type") != "ABSTENTION_OBSERVATION":
            continue
        pl = e.get("payload") or {}
        if pl.get("checkpoint_date_et") == checkpoint_date_et:
            return pl
    return None


async def lock_live_forecast(
    forecast: Any,
    snapshot: Dict[str, Any],
    root: Path | str = DEFAULT_ROOT,
    now: Optional[datetime] = None,
    entry_lookup=None,
    shadow_candidate: Optional[Dict[str, Any]] = None,
    premove: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Lock one pre-move forecast if and only if the live checkpoint is open.

    `premove` is the PRE-MOVE WATCH view that the dashboard displays. When it is
    supplied the ledger locks the exact per-horizon 4H/8H distributions the user
    saw, rather than the base engine's single distribution duplicated into both
    slots. Display/lock parity is verifiable afterwards via the recorded
    premove.forecast_id and premove.evidence_hash.
    """
    root = Path(root)
    now = (now or utcnow()).astimezone(timezone.utc)
    state = checkpoint_state(now)
    if not state["eligible_now"]:
        return {"ok": True, "created": False, "reason": "OUTSIDE_LIVE_CHECKPOINT_NO_BACKFILL", "checkpoint": state}

    existing = _has_lock_for_date(root, state["checkpoint_date_et"])
    if existing:
        return {"ok": True, "created": False, "reason": "CHECKPOINT_ALREADY_IMMUTABLY_LOCKED", "forecast_id": existing["forecast_id"]}

    seal = verify_campaign_seal()
    if not seal.get("ok"):
        return {"ok": False, "created": False, "reason": "CAMPAIGN_SEAL_OR_MODEL_FINGERPRINT_INVALID", "campaign_seal": seal}
    if shadow_candidate is not None and seal.get("policy", {}).get("shadow_candidate") is None:
        return {"ok": False, "created": False, "reason": "UNSEALED_SHADOW_CANDIDATE_FORBIDDEN"}

    base = _forecast_values(forecast, premove)
    generated = _parse_dt(base["generated_at"]) if base.get("generated_at") else now
    if generated > now + timedelta(seconds=5):
        return {"ok": False, "created": False, "reason": "FORECAST_TIMESTAMP_IN_FUTURE"}
    if now - generated > timedelta(minutes=15):
        return {"ok": False, "created": False, "reason": "FORECAST_NOT_FRESH_ENOUGH_TO_LOCK"}

    # V6.6.2 EVIDENCE-QUALITY GATE.
    # A Forward-OOS lock is IMMUTABLE and permanently enters the out-of-sample
    # record. Before this gate the only checks were timing, seal and contract, so a
    # forecast built on demo/degraded/zero-coverage evidence could be sealed forever
    # and would then be scored as a genuine out-of-sample observation. An unusable
    # observation is worse than no observation: it silently poisons the campaign.
    _status = str(base.get("status") or "").upper()
    _status_tokens = {t for t in re.split(r"[^A-Z0-9]+", _status) if t}
    _bad = {"DEMO", "SIMULATED", "SAMPLE", "PLACEHOLDER", "MOCK", "ERROR",
            "FAIL", "FAILED", "DOWN", "DEAD", "MISSING", "STALE", "UNAVAILABLE"}
    if _status_tokens & _bad:
        return {"ok": False, "created": False,
                "reason": "EVIDENCE_QUALITY_TOO_LOW_TO_LOCK",
                "detail": "forecast status %r is not a live evidence state" % _status,
                "forecast_status": _status}

    _cov = _float(base.get("data_coverage"))
    _icov = _float(base.get("intelligence_coverage"))
    _min_cov = float(os.getenv("FIA_FOOS_MIN_DATA_COVERAGE", "0.50") or 0.50)
    _min_icov = float(os.getenv("FIA_FOOS_MIN_INTELLIGENCE_COVERAGE", "0.30") or 0.30)
    if _cov is None or _cov < _min_cov or _icov is None or _icov < _min_icov:
        return {"ok": False, "created": False,
                "reason": "EVIDENCE_COVERAGE_TOO_LOW_TO_LOCK",
                "data_coverage": _cov, "intelligence_coverage": _icov,
                "min_data_coverage": _min_cov, "min_intelligence_coverage": _min_icov}

    # DISPLAYED ABSTENTION MUST NOT BE LOCKED AS A DIRECTIONAL OBSERVATION.
    # If the pre-move view the trader saw abstained on either horizon, or the
    # overall pre-move state is an abstention/degraded state, this checkpoint is
    # not a directional out-of-sample observation.
    if isinstance(premove, dict) and premove:
        _pm_state = str(premove.get("state") or "").upper()
        if _pm_state in {"NO_EDGE", "MISSING_DATA", "DEGRADED", "STALE"}:
            return {"ok": False, "created": False,
                    "reason": "PREMOVE_STATE_NOT_LOCKABLE",
                    "premove_state": _pm_state}
        _pm_h = premove.get("horizons") or {}
        _abstained = [h for h in ("4h", "8h")
                      if str((_pm_h.get(h) or {}).get("direction") or "").upper()
                      in {"NO_EDGE", "NEUTRAL", ""}]
        if _abstained:
            return {"ok": False, "created": False,
                    "reason": "PREMOVE_HORIZON_ABSTENTION_NOT_LOCKED_AS_DIRECTIONAL",
                    "abstained_horizons": _abstained}

    if str(base.get("direction") or "").upper() in {"NO_EDGE", "NEUTRAL", ""}:
        # An abstention is a legitimate research state but it is not a directional
        # out-of-sample observation and must not be scored as one.
        return {"ok": False, "created": False,
                "reason": "NO_EDGE_ABSTENTION_NOT_LOCKED_AS_DIRECTIONAL_OBSERVATION",
                "direction": base.get("direction")}

    contract_meta = _extract_contract(snapshot)
    require_explicit = True
    if not contract_meta["explicit"]:
        return {"ok": False, "created": False, "reason": "EXPLICIT_NQ_CONTRACT_REQUIRED", "contract": contract_meta}
    contract = contract_meta.get("contract")
    if not contract:
        return {"ok": False, "created": False, "reason": "NQ_CONTRACT_UNAVAILABLE"}

    if entry_lookup is None:
        return {"ok": False, "created": False, "reason": "ENTRY_LOOKUP_REQUIRED_BY_CALLER"}
    entry = entry_lookup(contract, now)
    if asyncio.iscoroutine(entry):
        entry = await entry
    if not isinstance(entry, dict) or _float(entry.get("close")) is None:
        return {"ok": False, "created": False, "reason": "FRESH_EXPLICIT_CONTRACT_ENTRY_UNAVAILABLE", "contract": contract}

    forecast_id = f"NQ-FOOS-{state['checkpoint_date_et'].replace('-', '')}"
    fingerprint = model_fingerprint()
    target4 = now + timedelta(hours=4)
    target8 = now + timedelta(hours=8)

    models: Dict[str, Any] = {MODEL_NAME: base}
    if shadow_candidate is not None:
        candidate = _primitive(shadow_candidate)
        if not isinstance(candidate, dict):
            raise ValueError("shadow_candidate must be a dict")
        # A candidate is valid only if supplied at lock time; it can never be
        # appended retrospectively after an outcome exists.
        models["SHADOW_CANDIDATE"] = candidate

    evidence_bundle = {
        "schema_version": SCHEMA_VERSION,
        "program": PROGRAM_NAME,
        "forecast_id": forecast_id,
        "captured_at_utc": _iso(now),
        "checkpoint": state,
        "entry": {
            "contract": contract,
            "contract_source": contract_meta,
            "price": _float(entry.get("close")),
            "completed_bar_end_utc": entry.get("bar_end_utc"),
            "bar_age_minutes": entry.get("age_minutes"),
            "price_source": entry.get("source"),
            "vendor_symbol": entry.get("vendor_symbol"),
        },
        "models": models,
        "model_fingerprint": fingerprint,
        "campaign_seal": {
            "campaign_id": seal.get("campaign_id"),
            "sealed_at_utc": seal.get("sealed_at_utc"),
            "seal_path": seal.get("path"),
            "model_fingerprint_match": seal.get("model_fingerprint_match"),
        },
        "provider_snapshot": _primitive(snapshot),
        "truth_policy": {
            "new_forward_only": True,
            "historical_import_allowed": False,
            "legacy_observed_holdout_eligible": False,
            "missed_checkpoint_backfill_allowed": False,
            "forecast_edit_allowed": False,
            "forecast_delete_api": False,
        },
    }
    evidence_meta = _write_evidence_once(root, forecast_id, evidence_bundle)

    payload = {
        "program": PROGRAM_NAME,
        "checkpoint_date_et": state["checkpoint_date_et"],
        "scheduled_checkpoint_et": state["scheduled_checkpoint_et"],
        "locked_at_utc": _iso(now),
        "targets": {"4h": _iso(target4), "8h": _iso(target8)},
        "entry": evidence_bundle["entry"],
        "models": models,
        "model_fingerprint": fingerprint,
        "campaign": {
            "campaign_id": seal.get("campaign_id"),
            "sealed_at_utc": seal.get("sealed_at_utc"),
            "model_fingerprint_digest": seal.get("sealed_model_fingerprint", {}).get("digest"),
        },
        "evidence": evidence_meta,
        "eligibility": {
            "genuinely_new_forward": True,
            "legacy_holdout_reused": False,
            "eligible_for_future_promotion_evaluation": True,
        },
    }
    try:
        event = _append_event(root, "FORECAST_LOCK", forecast_id, payload, now)
    except FileExistsError:
        existing = _has_lock_for_date(root, state["checkpoint_date_et"])
        return {"ok": True, "created": False, "reason": "CHECKPOINT_ALREADY_IMMUTABLY_LOCKED", "forecast_id": existing.get("forecast_id") if existing else forecast_id}
    return {"ok": True, "created": True, "forecast_id": forecast_id, "event_hash": event["event_hash"], "evidence_sha256": evidence_meta["sha256"]}


def _resolved_keys(root: Path) -> set[Tuple[str, int]]:
    keys: set[Tuple[str, int]] = set()
    for p in _event_files(root):
        e = _read_event(p)
        et = e.get("event_type")
        if et == "RESOLUTION_4H":
            keys.add((str(e.get("forecast_id")), 4))
        elif et == "RESOLUTION_8H":
            keys.add((str(e.get("forecast_id")), 8))
    return keys


def _outcome(entry: float, future: float) -> str:
    if future > entry:
        return "BULLISH"
    if future < entry:
        return "BEARISH"
    return "NEUTRAL"


async def resolve_due_forecasts(
    hub: Any,
    root: Path | str = DEFAULT_ROOT,
    now: Optional[datetime] = None,
    price_lookup=None,
) -> Dict[str, Any]:
    """Append immutable 4H/8H resolution events for completed targets."""
    root = Path(root)
    now = (now or utcnow()).astimezone(timezone.utc)
    audit = verify_ledger(root)
    if not audit["ok"]:
        return {"ok": False, "resolved": 0, "reason": "LEDGER_INTEGRITY_FAILURE", "audit": audit}
    done = _resolved_keys(root)
    appended = 0
    pending_due = 0

    for lock in _locks(root):
        payload = lock.get("payload", {})
        fid = str(lock.get("forecast_id"))
        contract = str(payload.get("entry", {}).get("contract") or "")
        entry = _float(payload.get("entry", {}).get("price"))
        base = payload.get("models", {}).get(MODEL_NAME, {})
        if not contract or entry is None:
            continue
        for hours in (4, 8):
            if (fid, hours) in done:
                continue
            target_raw = payload.get("targets", {}).get(f"{hours}h")
            if not target_raw:
                continue
            target = _parse_dt(target_raw)
            if target > now:
                continue
            pending_due += 1
            if price_lookup is None:
                result = await explicit_contract_completed_close(hub, contract, target, max_age_minutes=30.0)
            else:
                result = price_lookup(contract, target)
                if asyncio.iscoroutine(result):
                    result = await result
            future = _float(result.get("close")) if isinstance(result, dict) else None
            if future is None:
                continue
            actual = _outcome(entry, future)
            predictions: Dict[str, Any] = {}
            for model_name, pred in (payload.get("models") or {}).items():
                direction = str((pred or {}).get("direction") or "").upper()
                predictions[model_name] = {
                    "direction": direction,
                    "correct": direction == actual if direction in {"BULLISH", "BEARISH"} else None,
                }
            resolution_payload = {
                "horizon_hours": hours,
                "target_utc": _iso(target),
                "resolved_at_utc": _iso(now),
                "entry_contract_frozen": contract,
                "entry_price": entry,
                "outcome_price": future,
                "outcome_completed_bar_end_utc": result.get("bar_end_utc") if isinstance(result, dict) else None,
                "outcome_price_source": result.get("source") if isinstance(result, dict) else None,
                "outcome_vendor_symbol": result.get("vendor_symbol") if isinstance(result, dict) else None,
                "actual_direction": actual,
                "model_results": predictions,
                "future_information_used_for_prediction": False,
                "resolution_only": True,
            }
            try:
                _append_event(root, f"RESOLUTION_{hours}H", fid, resolution_payload, now)
            except FileExistsError:
                done.add((fid, hours))
                continue
            done.add((fid, hours))
            appended += 1

    return {"ok": True, "resolved": appended, "due_unresolved_after_run": max(0, pending_due - appended), "ledger": verify_ledger(root)}


def records(root: Path | str = DEFAULT_ROOT) -> List[Dict[str, Any]]:
    root = Path(root)
    by_id: Dict[str, Dict[str, Any]] = {}
    for path in _event_files(root):
        event = _read_event(path)
        fid = str(event.get("forecast_id") or "")
        if event.get("event_type") == "FORECAST_LOCK":
            p = event.get("payload", {})
            by_id[fid] = {
                "forecast_id": fid,
                "lock_event_hash": event.get("event_hash"),
                "locked_at_utc": p.get("locked_at_utc"),
                "checkpoint_date_et": p.get("checkpoint_date_et"),
                "entry": p.get("entry"),
                "targets": p.get("targets"),
                "models": p.get("models") or {},
                "model_fingerprint": p.get("model_fingerprint"),
                "evidence": p.get("evidence"),
                "4h": None,
                "8h": None,
            }
        elif event.get("event_type") in {"RESOLUTION_4H", "RESOLUTION_8H"} and fid in by_id:
            h = "4h" if event["event_type"] == "RESOLUTION_4H" else "8h"
            by_id[fid][h] = {**event.get("payload", {}), "resolution_event_hash": event.get("event_hash")}
    return sorted(by_id.values(), key=lambda r: r.get("locked_at_utc") or "")


def _wilson(correct: int, n: int) -> Optional[List[float]]:
    if n <= 0:
        return None
    z = 1.959963984540054
    p = correct / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / den
    return [round(100 * (center - margin), 2), round(100 * (center + margin), 2)]


def _model_metrics(rows: Sequence[Dict[str, Any]], model_name: str, hours: int) -> Dict[str, Any]:
    resolved = []
    for row in rows:
        outcome = row.get(f"{hours}h")
        pred = (row.get("models") or {}).get(model_name)
        if not outcome or not isinstance(pred, dict):
            continue
        actual = str(outcome.get("actual_direction") or "").upper()
        direction = str(pred.get("direction") or "").upper()
        horizon_probs = pred.get("horizon_probabilities") or {}
        hp = horizon_probs.get(f"{hours}h") if isinstance(horizon_probs, dict) else None
        p = _float((hp or {}).get("bullish_probability")) if isinstance(hp, dict) else None
        if p is None:
            p = _float(pred.get("bullish_probability"))
        if actual not in {"BULLISH", "BEARISH"} or direction not in {"BULLISH", "BEARISH"} or p is None:
            continue
        p = max(0.0, min(1.0, p / 100.0))
        y = 1.0 if actual == "BULLISH" else 0.0
        resolved.append((row, pred, actual, direction == actual, p, y))
    n = len(resolved)
    correct = sum(1 for *_, c, p, y in resolved if c) if resolved else 0
    # The starred expression above is legal but opaque; recompute explicitly for clarity.
    correct = sum(1 for item in resolved if item[3])
    brier = sum((item[4] - item[5]) ** 2 for item in resolved) / n if n else None

    bins = []
    ece = 0.0
    for lo, hi in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.000001)):
        vals = [item for item in resolved if lo <= item[4] < hi]
        if not vals:
            continue
        avg = sum(v[4] for v in vals) / len(vals)
        freq = sum(v[5] for v in vals) / len(vals)
        ece += len(vals) / n * abs(avg - freq)
        bins.append({"band": f"{int(lo*100)}-{100 if hi > 1 else int(hi*100)}%", "n": len(vals), "mean_probability": round(avg * 100, 2), "bullish_frequency": round(freq * 100, 2), "gap_pp": round(abs(avg - freq) * 100, 2)})

    return {
        "n": n,
        "correct": correct,
        "incorrect": n - correct,
        "accuracy": round(correct / n * 100, 2) if n else None,
        "wilson95": _wilson(correct, n),
        "brier": round(brier, 6) if brier is not None else None,
        "ece": round(ece, 6) if n else None,
        "calibration_bins": bins,
    }


def _group_metrics(rows: Sequence[Dict[str, Any]], hours: int, key_fn) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        base = (row.get("models") or {}).get(MODEL_NAME, {})
        key = str(key_fn(base) or "UNKNOWN")
        groups.setdefault(key, []).append(row)
    out = []
    for key, grp in sorted(groups.items()):
        m = _model_metrics(grp, MODEL_NAME, hours)
        if m["n"]:
            out.append({"group": key, **{k: v for k, v in m.items() if k != "calibration_bins"}})
    return out


def _confidence_bucket(base: Dict[str, Any]) -> str:
    c = _float(base.get("confidence"))
    if c is None:
        return "UNKNOWN"
    if c < 55:
        return "<55"
    if c < 65:
        return "55-64.99"
    if c < 75:
        return "65-74.99"
    return ">=75"


def promotion_gate(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Conservative candidate-vs-BASE gate on the same genuinely-new records."""
    candidate_present = any("SHADOW_CANDIDATE" in (r.get("models") or {}) for r in rows)
    if not candidate_present:
        return {
            "verdict": "NO_PROMOTION",
            "reason": "NO_SHADOW_CANDIDATE_WAS_LOCKED_PRE_MOVE",
            "production_model": MODEL_NAME,
            "minimum_new_forward_resolved_per_horizon": TARGET_PROMOTION_N,
            "legacy_observed_holdout_eligible": False,
        }

    details = {}
    pass_horizons = []
    for h in (4, 8):
        base = _model_metrics(rows, MODEL_NAME, h)
        cand = _model_metrics(rows, "SHADOW_CANDIDATE", h)
        accuracy_delta = None if base["accuracy"] is None or cand["accuracy"] is None else cand["accuracy"] - base["accuracy"]
        brier_delta = None if base["brier"] is None or cand["brier"] is None else cand["brier"] - base["brier"]
        ece_delta = None if base["ece"] is None or cand["ece"] is None else cand["ece"] - base["ece"]
        eligible = (
            base["n"] >= TARGET_PROMOTION_N
            and cand["n"] == base["n"]
            and accuracy_delta is not None and accuracy_delta >= 0.0
            and brier_delta is not None and brier_delta <= -0.005
            and ece_delta is not None and ece_delta <= 0.02
        )
        details[f"{h}h"] = {
            "base": base,
            "candidate": cand,
            "accuracy_delta_pp": round(accuracy_delta, 4) if accuracy_delta is not None else None,
            "brier_delta_candidate_minus_base": round(brier_delta, 6) if brier_delta is not None else None,
            "ece_delta_candidate_minus_base": round(ece_delta, 6) if ece_delta is not None else None,
            "horizon_gate_pass": eligible,
        }
        pass_horizons.append(eligible)

    avg_acc_delta = statistics.mean([
        details["4h"]["accuracy_delta_pp"] or 0.0,
        details["8h"]["accuracy_delta_pp"] or 0.0,
    ])
    overall = all(pass_horizons) and avg_acc_delta >= 2.0
    return {
        "verdict": "PROMOTION_ELIGIBLE_NOT_AUTO_DEPLOYED" if overall else "NO_PROMOTION",
        "production_model": MODEL_NAME,
        "requirements": {
            "n_each_horizon": TARGET_PROMOTION_N,
            "candidate_accuracy_not_worse_each_horizon": True,
            "candidate_brier_improvement_each_horizon": ">=0.005",
            "candidate_ece_not_worse_by_more_than": 0.02,
            "average_accuracy_improvement_pp": ">=2.0",
        },
        "legacy_observed_holdout_eligible": False,
        "old_holdout_permanently_disqualified_as_untouched": True,
        "details": details,
        "average_accuracy_delta_pp": round(avg_acc_delta, 4),
    }


def forward_report(root: Path | str = DEFAULT_ROOT) -> Dict[str, Any]:
    root = Path(root)
    audit = verify_ledger(root)
    rows = records(root) if audit["ok"] else []
    m4 = _model_metrics(rows, MODEL_NAME, 4)
    m8 = _model_metrics(rows, MODEL_NAME, 8)
    fully = sum(1 for r in rows if r.get("4h") and r.get("8h"))
    min_resolved = min(m4["n"], m8["n"])
    if min_resolved >= TARGET_PROMOTION_N:
        stage = "TARGET_SAMPLE_REACHED"
    elif min_resolved >= MIN_REPORT_N:
        stage = "EARLY_FORWARD_EVIDENCE"
    else:
        stage = "COLLECTING_NEW_UNSEEN_FORECASTS"
    fingerprints = sorted({
        str((r.get("model_fingerprint") or {}).get("digest") or "")
        for r in rows if (r.get("model_fingerprint") or {}).get("digest")
    })
    campaign_seal = verify_campaign_seal()
    return {
        "ok": audit["ok"] and campaign_seal.get("ok", False) and len(fingerprints) <= 1,
        "program": PROGRAM_NAME,
        "campaign_seal": campaign_seal,
        "observed_model_fingerprints": fingerprints,
        "mixed_model_versions": len(fingerprints) > 1,
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "new_forward_forecasts_locked": len(rows),
        "fully_resolved_4h_8h": fully,
        "minimum_report_sample": MIN_REPORT_N,
        "target_promotion_sample": TARGET_PROMOTION_N,
        "base_fia": {"4h": m4, "8h": m8},
        "confidence_buckets": {
            "4h": _group_metrics(rows, 4, _confidence_bucket),
            "8h": _group_metrics(rows, 8, _confidence_bucket),
        },
        "regime_performance": {
            "4h": _group_metrics(rows, 4, lambda b: b.get("regime")),
            "8h": _group_metrics(rows, 8, lambda b: b.get("regime")),
        },
        "promotion": promotion_gate(rows),
        "ledger_integrity": audit,
        "scientific_policy": {
            "historical_tuning_after_program_start": False,
            "old_observed_holdout_recycled": False,
            "old_observed_holdout_untouched_rows": 0,
            "future_information_for_prediction": False,
            "loss_deletion_allowed": False,
            "forecast_edit_allowed": False,
            "missed_checkpoint_backfill_allowed": False,
            "base_replaced_automatically": False,
            "new_forward_oos_required_for_promotion": True,
        },
        "warning": "Forward forecasts are the only promotion-eligible evidence. Historical/legacy holdouts are reference-only and cannot be relabeled untouched.",
    }
