"""SIMONS SHADOW LAB V1.

A deliberately isolated research layer for CLEAR NASDAQ FIA.

Scientific rules:
- Production Forward-OOS files are READ ONLY. This module never imports or calls
  production append/write helpers.
- Existing locked forecasts and outcomes are evidence, never training targets
  that can be silently rewritten.
- Discovery results are exploratory only.
- A candidate is frozen before it can produce a valid forward shadow decision.
- Only production locks created after candidate freeze can become candidate
  validation decisions.
- Outcome resolution is attached later as a separate immutable shadow event.
- No automatic production promotion exists in this package.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

LAB_SCHEMA_VERSION = "SIMONS_SHADOW_LAB_V1"
MODEL_NAME = "BASE_FIA"
GENESIS = "GENESIS"


def _primitive(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _primitive(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple, set)):
        return [_primitive(v) for v in value]
    return str(value)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(_primitive(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_dt(value: Any) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        return out if math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def _read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: %s" % path)
    return value


def _write_new_json(path: Path, payload: Dict[str, Any]) -> None:
    """Create once. No update API exists by design."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_bytes(payload) + b"\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    try:
        path.chmod(0o444)
    except OSError:
        pass


def _source_event_paths(source_root: Path) -> List[Path]:
    events_dir = source_root / "events"
    if not events_dir.exists() or not events_dir.is_dir():
        return []
    return sorted(p for p in events_dir.glob("*.json") if p.is_file())


def verify_source_read_only(source_root: Path) -> Dict[str, Any]:
    """Verify the production ledger without creating or changing source files."""
    source_root = Path(source_root)
    issues: List[str] = []
    files = _source_event_paths(source_root)
    prev = GENESIS
    expected_seq = 1
    locks: Dict[str, Dict[str, Any]] = {}
    resolutions: Dict[Tuple[str, int], Dict[str, Any]] = {}
    source_hashes: Dict[str, str] = {}

    seal_path = source_root / "FORWARD_OOS_CAMPAIGN_SEAL.json"
    seal = None
    if seal_path.exists():
        try:
            seal = _read_json(seal_path)
            unsigned = dict(seal)
            claimed = str(unsigned.pop("seal_hash", ""))
            if claimed and claimed != sha256_bytes(canonical_bytes(unsigned)):
                issues.append("campaign_seal_hash")
            source_hashes[str(seal_path.name)] = sha256_file(seal_path)
        except Exception as exc:
            issues.append("campaign_seal_unreadable:%s" % type(exc).__name__)
    else:
        issues.append("campaign_seal_missing")

    for path in files:
        source_hashes[str(path.relative_to(source_root))] = sha256_file(path)
        try:
            event = _read_json(path)
        except Exception as exc:
            issues.append("unreadable_event:%s:%s" % (path.name, type(exc).__name__))
            continue
        seq = event.get("seq")
        if seq != expected_seq:
            issues.append("sequence:%s:expected=%s:got=%s" % (path.name, expected_seq, seq))
        if event.get("prev_event_hash") != prev:
            issues.append("chain_prev:%s" % path.name)
        claimed = str(event.get("event_hash") or "")
        unsigned = dict(event)
        unsigned.pop("event_hash", None)
        if claimed != sha256_bytes(canonical_bytes(unsigned)):
            issues.append("event_hash:%s" % path.name)

        event_type = str(event.get("event_type") or "")
        forecast_id = str(event.get("forecast_id") or "")
        if event_type == "FORECAST_LOCK":
            if forecast_id in locks:
                issues.append("duplicate_forecast_lock:%s" % forecast_id)
            locks[forecast_id] = event
            evidence = (event.get("payload") or {}).get("evidence") or {}
            rel = evidence.get("path")
            digest = evidence.get("sha256")
            if not rel or not digest:
                issues.append("missing_evidence_ref:%s" % forecast_id)
            else:
                ep = source_root / str(rel)
                if not ep.exists():
                    issues.append("missing_evidence_file:%s" % forecast_id)
                else:
                    actual_digest = sha256_file(ep)
                    source_hashes[str(ep.relative_to(source_root))] = actual_digest
                    if actual_digest != digest:
                        issues.append("evidence_hash:%s" % forecast_id)
        elif event_type in {"RESOLUTION_4H", "RESOLUTION_8H"}:
            hours = 4 if event_type == "RESOLUTION_4H" else 8
            if forecast_id not in locks:
                issues.append("resolution_without_prior_lock:%s:%s" % (forecast_id, hours))
            key = (forecast_id, hours)
            if key in resolutions:
                issues.append("duplicate_resolution:%s:%s" % key)
            resolutions[key] = event

        prev = claimed
        expected_seq += 1

    head_path = source_root / "LEDGER_HEAD.json"
    if files:
        if not head_path.exists():
            issues.append("ledger_head_missing")
        else:
            try:
                head = _read_json(head_path)
                source_hashes[str(head_path.name)] = sha256_file(head_path)
                unsigned = dict(head)
                anchor = str(unsigned.pop("anchor_hash", ""))
                if anchor != sha256_bytes(canonical_bytes(unsigned)):
                    issues.append("ledger_head_anchor_hash")
                if int(head.get("events", -1)) != len(files):
                    issues.append("ledger_head_event_count")
                if str(head.get("head_event_hash") or "") != prev:
                    issues.append("ledger_head_event_hash")
            except Exception as exc:
                issues.append("ledger_head_unreadable:%s" % type(exc).__name__)

    return {
        "ok": not issues,
        "schema_version": LAB_SCHEMA_VERSION,
        "source_exists": source_root.exists(),
        "events": len(files),
        "forecast_locks": len(locks),
        "resolution_events": len(resolutions),
        "head_event_hash": prev,
        "campaign_id": (seal or {}).get("campaign_id") if isinstance(seal, dict) else None,
        "sealed_model_fingerprint_digest": (((seal or {}).get("model_fingerprint") or {}).get("digest")
                                            if isinstance(seal, dict) else None),
        "issues": issues,
        "source_hashes": source_hashes,
        "source_modified": False,
    }


def _events_index(source_root: Path) -> Tuple[Dict[str, Dict[str, Any]], Dict[Tuple[str, int], Dict[str, Any]]]:
    locks: Dict[str, Dict[str, Any]] = {}
    resolutions: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for path in _source_event_paths(source_root):
        event = _read_json(path)
        fid = str(event.get("forecast_id") or "")
        et = event.get("event_type")
        if et == "FORECAST_LOCK":
            locks[fid] = event
        elif et in {"RESOLUTION_4H", "RESOLUTION_8H"}:
            resolutions[(fid, 4 if et == "RESOLUTION_4H" else 8)] = event
    return locks, resolutions


def _horizon_prediction(base: Dict[str, Any], hours: int) -> Dict[str, Any]:
    hp = (base.get("horizon_probabilities") or {}).get("%sh" % hours) or {}
    bull = _float(hp.get("bullish_probability"))
    bear = _float(hp.get("bearish_probability"))
    if bull is None:
        bull = _float(base.get("bullish_probability"))
    if bear is None:
        bear = _float(base.get("bearish_probability"))
    direction = str(hp.get("direction") or base.get("direction") or "").upper()
    confidence = _float(hp.get("confidence"))
    if confidence is None:
        confidence = _float(base.get("confidence"))
    return {
        "bullish_probability": bull,
        "bearish_probability": bear,
        "direction": direction,
        "confidence": confidence,
        "state": str(hp.get("state") or "").upper() or None,
        "actionable": hp.get("actionable"),
        "source": hp.get("source"),
    }


def _row_from_lock(lock: Dict[str, Any], resolutions: Dict[Tuple[str, int], Dict[str, Any]]) -> Dict[str, Any]:
    payload = lock.get("payload") or {}
    models = payload.get("models") or {}
    base = models.get(MODEL_NAME) or {}
    fid = str(lock.get("forecast_id") or "")
    row: Dict[str, Any] = {
        "forecast_id": fid,
        "lock_event_hash": lock.get("event_hash"),
        "locked_at_utc": payload.get("locked_at_utc") or lock.get("created_at_utc"),
        "checkpoint_date_et": payload.get("checkpoint_date_et"),
        "entry": payload.get("entry") or {},
        "campaign": payload.get("campaign") or {},
        "eligibility": payload.get("eligibility") or {},
        "base": {
            "direction": str(base.get("direction") or "").upper(),
            "confidence": _float(base.get("confidence")),
            "regime": str(base.get("regime") or "UNKNOWN").upper(),
            "status": base.get("status"),
            "score": _float(base.get("score")),
            "data_coverage": _float(base.get("data_coverage")),
            "intelligence_coverage": _float(base.get("intelligence_coverage")),
            "premove": base.get("premove") or {},
            "source_status": base.get("source_status") or {},
            "signals": base.get("signals") or [],
            "h4": _horizon_prediction(base, 4),
            "h8": _horizon_prediction(base, 8),
        },
        "outcomes": {},
    }
    for hours in (4, 8):
        event = resolutions.get((fid, hours))
        if event:
            rp = event.get("payload") or {}
            row["outcomes"]["%sh" % hours] = {
                "actual_direction": str(rp.get("actual_direction") or "").upper(),
                "entry_price": _float(rp.get("entry_price")),
                "outcome_price": _float(rp.get("outcome_price")),
                "target_utc": rp.get("target_utc"),
                "resolved_at_utc": rp.get("resolved_at_utc"),
                "resolution_event_hash": event.get("event_hash"),
            }
    return row


def build_rows(source_root: Path) -> List[Dict[str, Any]]:
    audit = verify_source_read_only(source_root)
    if not audit["ok"]:
        raise RuntimeError("source integrity failure: %s" % ";".join(audit["issues"]))
    locks, resolutions = _events_index(Path(source_root))
    rows = [_row_from_lock(lock, resolutions) for lock in locks.values()]
    return sorted(rows, key=lambda row: str(row.get("locked_at_utc") or ""))


def _snapshot_core(source_root: Path, rows: Sequence[Dict[str, Any]], audit: Dict[str, Any], created_at: datetime) -> Dict[str, Any]:
    completed_4h = sum(1 for row in rows if "4h" in (row.get("outcomes") or {}))
    completed_8h = sum(1 for row in rows if "8h" in (row.get("outcomes") or {}))
    core = {
        "schema_version": LAB_SCHEMA_VERSION,
        "created_at_utc": created_at.astimezone(timezone.utc).isoformat(),
        "source_root": str(Path(source_root).resolve()),
        "campaign_id": audit.get("campaign_id"),
        "sealed_model_fingerprint_digest": audit.get("sealed_model_fingerprint_digest"),
        "source_head_event_hash": audit.get("head_event_hash"),
        "source_hashes": audit.get("source_hashes") or {},
        "row_count": len(rows),
        "completed_4h": completed_4h,
        "completed_8h": completed_8h,
        "forecast_ids": [row.get("forecast_id") for row in rows],
        "rows_sha256": sha256_bytes(canonical_bytes(list(rows))),
        "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
        "production_modified": False,
    }
    core["snapshot_id"] = "SSL1-" + sha256_bytes(canonical_bytes(core))[:24]
    return core


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    horizon_hours: int
    conditions: Sequence[Mapping[str, Any]]
    predicted_direction: str
    discovery_snapshot_id: str
    discovery_forecast_ids: Sequence[str]
    tests_run_before_selection: int
    notes: str = ""

    def normalized(self) -> Dict[str, Any]:
        direction = str(self.predicted_direction or "").upper()
        if self.horizon_hours not in (4, 8):
            raise ValueError("horizon_hours must be 4 or 8")
        if direction not in {"BULLISH", "BEARISH", "FOLLOW_FIA"}:
            raise ValueError("predicted_direction must be BULLISH, BEARISH or FOLLOW_FIA")
        if self.tests_run_before_selection < 1:
            raise ValueError("tests_run_before_selection must be >= 1")
        allowed_ops = {"eq", "ne", "gte", "lte", "gt", "lt", "in"}
        normalized_conditions = []
        for raw in self.conditions:
            field = str(raw.get("field") or "").strip()
            op = str(raw.get("op") or "").strip().lower()
            if not field or op not in allowed_ops:
                raise ValueError("invalid candidate condition")
            normalized_conditions.append({"field": field, "op": op, "value": _primitive(raw.get("value"))})
        return {
            "name": self.name,
            "horizon_hours": self.horizon_hours,
            "conditions": normalized_conditions,
            "predicted_direction": direction,
            "discovery_snapshot_id": self.discovery_snapshot_id,
            "discovery_forecast_ids": sorted(set(str(x) for x in self.discovery_forecast_ids)),
            "tests_run_before_selection": int(self.tests_run_before_selection),
            "notes": self.notes,
        }


def _feature_map(row: Dict[str, Any], hours: int) -> Dict[str, Any]:
    base = row.get("base") or {}
    h = base.get("h%s" % hours) or {}
    bull = _float(h.get("bullish_probability"))
    bear = _float(h.get("bearish_probability"))
    confidence = _float(h.get("confidence"))
    edge = abs((bull or 50.0) - (bear or 50.0)) if bull is not None and bear is not None else None
    return {
        "forecast_id": row.get("forecast_id"),
        "fia_direction": str(h.get("direction") or base.get("direction") or "").upper(),
        "bullish_probability": bull,
        "bearish_probability": bear,
        "confidence": confidence,
        "edge_points": edge,
        "regime": str(base.get("regime") or "UNKNOWN").upper(),
        "status": str(base.get("status") or "").upper(),
        "data_coverage": _float(base.get("data_coverage")),
        "intelligence_coverage": _float(base.get("intelligence_coverage")),
        "actionable": h.get("actionable"),
        "horizon_state": h.get("state"),
    }


def _match_condition(features: Dict[str, Any], condition: Mapping[str, Any]) -> bool:
    field = str(condition.get("field"))
    op = str(condition.get("op"))
    expected = condition.get("value")
    actual = features.get(field)
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "in":
        return actual in (expected or [])
    if actual is None or expected is None:
        return False
    try:
        a = float(actual)
        b = float(expected)
    except (TypeError, ValueError):
        return False
    if op == "gte":
        return a >= b
    if op == "lte":
        return a <= b
    if op == "gt":
        return a > b
    if op == "lt":
        return a < b
    return False


def _candidate_fires(candidate: Dict[str, Any], row: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    hours = int(candidate["spec"]["horizon_hours"])
    features = _feature_map(row, hours)
    conditions = candidate["spec"].get("conditions") or []
    return all(_match_condition(features, cond) for cond in conditions), features


def _candidate_direction(candidate: Dict[str, Any], features: Dict[str, Any]) -> Optional[str]:
    direction = str(candidate["spec"].get("predicted_direction") or "").upper()
    if direction == "FOLLOW_FIA":
        direction = str(features.get("fia_direction") or "").upper()
    return direction if direction in {"BULLISH", "BEARISH"} else None


def _binomial_upper_tail(k: int, n: int, p: float = 0.5) -> float:
    if n <= 0 or k < 0 or k > n:
        return 1.0
    total = 0.0
    for i in range(k, n + 1):
        total += math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    return min(1.0, max(0.0, total))


def _bh_qvalues(pvalues: Sequence[float]) -> List[float]:
    m = len(pvalues)
    if not m:
        return []
    ordered = sorted(enumerate(pvalues), key=lambda pair: pair[1])
    q = [1.0] * m
    running = 1.0
    for rank_from_end in range(m - 1, -1, -1):
        idx, p = ordered[rank_from_end]
        rank = rank_from_end + 1
        running = min(running, p * m / rank)
        q[idx] = min(1.0, running)
    return q


def discover_threshold_grid(rows: Sequence[Dict[str, Any]], min_n: int = 12) -> Dict[str, Any]:
    """Predeclared interpretable grid. Returns all tests; never auto-promotes a winner."""
    tests: List[Dict[str, Any]] = []
    prob_thresholds = (55.0, 60.0, 65.0, 70.0)
    conf_thresholds = (0.0, 20.0, 40.0, 60.0)
    for hours in (4, 8):
        for direction in ("BULLISH", "BEARISH"):
            prob_field = "bullish_probability" if direction == "BULLISH" else "bearish_probability"
            for pthr in prob_thresholds:
                for cthr in conf_thresholds:
                    selected = []
                    for row in rows:
                        outcome = (row.get("outcomes") or {}).get("%sh" % hours)
                        if not outcome:
                            continue
                        f = _feature_map(row, hours)
                        pval = _float(f.get(prob_field))
                        conf = _float(f.get("confidence"))
                        if pval is None or conf is None or pval < pthr or conf < cthr:
                            continue
                        actual = str(outcome.get("actual_direction") or "").upper()
                        if actual in {"BULLISH", "BEARISH"}:
                            selected.append(actual == direction)
                    n = len(selected)
                    correct = sum(1 for x in selected if x)
                    pvalue = _binomial_upper_tail(correct, n, 0.5) if n >= min_n else 1.0
                    tests.append({
                        "horizon_hours": hours,
                        "predicted_direction": direction,
                        "conditions": [
                            {"field": prob_field, "op": "gte", "value": pthr},
                            {"field": "confidence", "op": "gte", "value": cthr},
                        ],
                        "n": n,
                        "correct": correct,
                        "hit_rate": (correct / n) if n else None,
                        "p_value_vs_50pct": pvalue,
                        "eligible_min_n": n >= min_n,
                    })
    qvals = _bh_qvalues([float(item["p_value_vs_50pct"]) for item in tests])
    for item, q in zip(tests, qvals):
        item["bh_q_value"] = q
        item["status"] = "EXPLORATORY_ONLY_NOT_PROVEN"
    return {
        "schema_version": LAB_SCHEMA_VERSION,
        "method": "PREDECLARED_THRESHOLD_GRID",
        "tests_run": len(tests),
        "multiple_testing_control": "BENJAMINI_HOCHBERG_REPORTED_NOT_PROMOTION_GATE",
        "min_n": min_n,
        "results": tests,
        "automatic_candidate_selection": False,
        "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
    }


class ShadowLab:
    def __init__(self, source_root: Path, lab_root: Path):
        self.source_root = Path(source_root)
        self.lab_root = Path(lab_root)
        self.lab_root.mkdir(parents=True, exist_ok=True)

    def audit_source(self) -> Dict[str, Any]:
        return verify_source_read_only(self.source_root)

    def create_snapshot(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        audit = self.audit_source()
        if not audit["ok"]:
            raise RuntimeError("source integrity failure: %s" % ";".join(audit["issues"]))
        rows = build_rows(self.source_root)
        now = now or datetime.now(timezone.utc)
        core = _snapshot_core(self.source_root, rows, audit, now)
        snapshot_dir = self.lab_root / "snapshots" / core["snapshot_id"]
        manifest = dict(core)
        manifest["manifest_sha256"] = sha256_bytes(canonical_bytes(core))
        _write_new_json(snapshot_dir / "manifest.json", manifest)
        _write_new_json(snapshot_dir / "rows.json", {"rows": rows, "rows_sha256": core["rows_sha256"]})
        return manifest

    def load_snapshot(self, snapshot_id: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        base = self.lab_root / "snapshots" / snapshot_id
        manifest = _read_json(base / "manifest.json")
        rows_doc = _read_json(base / "rows.json")
        rows = rows_doc.get("rows") or []
        if sha256_bytes(canonical_bytes(rows)) != rows_doc.get("rows_sha256"):
            raise RuntimeError("snapshot rows hash mismatch")
        core = dict(manifest)
        claimed = str(core.pop("manifest_sha256", ""))
        if claimed != sha256_bytes(canonical_bytes(core)):
            raise RuntimeError("snapshot manifest hash mismatch")
        return manifest, rows

    def register_hypothesis(self, snapshot_id: str, hypothesis: Mapping[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
        self.load_snapshot(snapshot_id)
        now = now or datetime.now(timezone.utc)
        core = {
            "schema_version": LAB_SCHEMA_VERSION,
            "created_at_utc": now.astimezone(timezone.utc).isoformat(),
            "snapshot_id": snapshot_id,
            "hypothesis": _primitive(dict(hypothesis)),
            "status": "DISCOVERY_ONLY_NOT_PROVEN",
        }
        hid = "HYP-" + sha256_bytes(canonical_bytes(core))[:24]
        payload = {**core, "hypothesis_id": hid}
        payload["record_sha256"] = sha256_bytes(canonical_bytes(payload))
        _write_new_json(self.lab_root / "hypotheses" / (hid + ".json"), payload)
        return payload

    def freeze_candidate(self, spec: CandidateSpec, now: Optional[datetime] = None) -> Dict[str, Any]:
        normalized = spec.normalized()
        manifest, rows = self.load_snapshot(normalized["discovery_snapshot_id"])
        known_ids = {str(r.get("forecast_id")) for r in rows}
        discovery_ids = set(normalized["discovery_forecast_ids"])
        if not discovery_ids.issubset(known_ids):
            raise ValueError("candidate references forecast IDs outside discovery snapshot")
        now = now or datetime.now(timezone.utc)
        core = {
            "schema_version": LAB_SCHEMA_VERSION,
            "created_at_utc": now.astimezone(timezone.utc).isoformat(),
            "spec": normalized,
            "discovery_snapshot_rows_sha256": manifest.get("rows_sha256"),
            "status": "FORWARD_VALIDATION_READY_NOT_PROVEN",
            "automatic_production_promotion": False,
        }
        cid = "CAND-" + sha256_bytes(canonical_bytes(core))[:24]
        payload = {**core, "candidate_id": cid}
        payload["candidate_sha256"] = sha256_bytes(canonical_bytes(payload))
        _write_new_json(self.lab_root / "candidates" / (cid + ".json"), payload)
        return payload

    def load_candidate(self, candidate_id: str) -> Dict[str, Any]:
        payload = _read_json(self.lab_root / "candidates" / (candidate_id + ".json"))
        core = dict(payload)
        claimed = str(core.pop("candidate_sha256", ""))
        if claimed != sha256_bytes(canonical_bytes(core)):
            raise RuntimeError("candidate hash mismatch")
        return payload

    def _shadow_events(self, candidate_id: str) -> List[Dict[str, Any]]:
        path = self.lab_root / "validation" / candidate_id / "events"
        if not path.exists():
            return []
        events = []
        for p in sorted(path.glob("*.json")):
            event = _read_json(p)
            unsigned = dict(event)
            claimed = str(unsigned.pop("event_hash", ""))
            if claimed != sha256_bytes(canonical_bytes(unsigned)):
                raise RuntimeError("shadow validation event hash mismatch: %s" % p.name)
            events.append(event)
        prev = GENESIS
        for i, event in enumerate(events, 1):
            if event.get("seq") != i or event.get("prev_event_hash") != prev:
                raise RuntimeError("shadow validation chain mismatch")
            prev = event["event_hash"]
        return events

    def _append_shadow_event(self, candidate_id: str, event_type: str, forecast_id: str, payload: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        existing = self._shadow_events(candidate_id)
        for event in existing:
            if event.get("event_type") == event_type and event.get("forecast_id") == forecast_id:
                raise FileExistsError("immutable shadow event already exists")
        seq = len(existing) + 1
        prev = existing[-1]["event_hash"] if existing else GENESIS
        unsigned = {
            "schema_version": LAB_SCHEMA_VERSION,
            "seq": seq,
            "event_type": event_type,
            "candidate_id": candidate_id,
            "forecast_id": forecast_id,
            "created_at_utc": now.astimezone(timezone.utc).isoformat(),
            "prev_event_hash": prev,
            "payload": _primitive(payload),
        }
        event = {**unsigned, "event_hash": sha256_bytes(canonical_bytes(unsigned))}
        path = self.lab_root / "validation" / candidate_id / "events" / (
            "%08d_%s_%s.json" % (seq, event_type.lower(), forecast_id)
        )
        _write_new_json(path, event)
        return event

    def lock_candidate_decision(self, candidate_id: str, forecast_id: str, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Lock FIRE/NO_FIRE from a production FORECAST_LOCK only; outcome is not read."""
        candidate = self.load_candidate(candidate_id)
        audit = self.audit_source()
        if not audit["ok"]:
            raise RuntimeError("source integrity failure")
        locks, _ = _events_index(self.source_root)
        lock = locks.get(forecast_id)
        if lock is None:
            raise KeyError("production forecast lock not found")
        row = _row_from_lock(lock, {})
        lock_time = _parse_dt(row.get("locked_at_utc"))
        candidate_time = _parse_dt(candidate.get("created_at_utc"))
        if lock_time <= candidate_time:
            raise ValueError("forecast is not new after candidate freeze")
        if forecast_id in set(candidate["spec"].get("discovery_forecast_ids") or []):
            raise ValueError("discovery row cannot enter candidate validation")
        fires, features = _candidate_fires(candidate, row)
        predicted_direction = _candidate_direction(candidate, features) if fires else None
        now = now or datetime.now(timezone.utc)
        return self._append_shadow_event(candidate_id, "DECISION_LOCK", forecast_id, {
            "production_lock_event_hash": lock.get("event_hash"),
            "production_locked_at_utc": row.get("locked_at_utc"),
            "horizon_hours": candidate["spec"]["horizon_hours"],
            "decision": "FIRE" if fires else "NO_FIRE",
            "predicted_direction": predicted_direction,
            "features": features,
            "outcome_information_read": False,
            "production_modified": False,
        }, now)

    def resolve_candidate_decision(self, candidate_id: str, forecast_id: str, now: Optional[datetime] = None) -> Dict[str, Any]:
        candidate = self.load_candidate(candidate_id)
        hours = int(candidate["spec"]["horizon_hours"])
        events = self._shadow_events(candidate_id)
        decision = next((e for e in events if e.get("event_type") == "DECISION_LOCK" and e.get("forecast_id") == forecast_id), None)
        if decision is None:
            raise ValueError("decision must be locked before resolution")
        _, resolutions = _events_index(self.source_root)
        resolution = resolutions.get((forecast_id, hours))
        if resolution is None:
            raise ValueError("production outcome not yet resolved")
        rp = resolution.get("payload") or {}
        predicted = str((decision.get("payload") or {}).get("predicted_direction") or "").upper()
        actual = str(rp.get("actual_direction") or "").upper()
        correct = (predicted == actual) if predicted in {"BULLISH", "BEARISH"} and actual in {"BULLISH", "BEARISH"} else None
        now = now or datetime.now(timezone.utc)
        return self._append_shadow_event(candidate_id, "DECISION_RESOLUTION", forecast_id, {
            "production_resolution_event_hash": resolution.get("event_hash"),
            "horizon_hours": hours,
            "decision": (decision.get("payload") or {}).get("decision"),
            "predicted_direction": predicted or None,
            "actual_direction": actual or None,
            "correct": correct,
            "entry_price": _float(rp.get("entry_price")),
            "outcome_price": _float(rp.get("outcome_price")),
            "target_utc": rp.get("target_utc"),
            "resolved_at_utc": rp.get("resolved_at_utc"),
            "resolution_only": True,
            "production_modified": False,
        }, now)

    def candidate_report(self, candidate_id: str) -> Dict[str, Any]:
        candidate = self.load_candidate(candidate_id)
        events = self._shadow_events(candidate_id)
        decisions = {e["forecast_id"]: e for e in events if e.get("event_type") == "DECISION_LOCK"}
        resolutions = {e["forecast_id"]: e for e in events if e.get("event_type") == "DECISION_RESOLUTION"}
        fired = [e for e in decisions.values() if (e.get("payload") or {}).get("decision") == "FIRE"]
        resolved_fired = []
        for event in fired:
            res = resolutions.get(event["forecast_id"])
            if res is not None and (res.get("payload") or {}).get("correct") is not None:
                resolved_fired.append(res)
        n = len(resolved_fired)
        correct = sum(1 for e in resolved_fired if (e.get("payload") or {}).get("correct") is True)
        hit_rate = correct / n if n else None
        if n < 30:
            status = "INSUFFICIENT_SAMPLE_NOT_PROVEN"
        elif n < 50:
            status = "FORWARD_VALIDATING_NOT_PROVEN"
        else:
            status = "RESEARCH_REVIEW_ELIGIBLE_NOT_PRODUCTION_APPROVED"
        return {
            "schema_version": LAB_SCHEMA_VERSION,
            "candidate_id": candidate_id,
            "candidate_status": status,
            "forward_decisions": len(decisions),
            "fires": len(fired),
            "abstentions": len(decisions) - len(fired),
            "resolved_fires": n,
            "correct": correct,
            "hit_rate": hit_rate,
            "automatic_production_promotion": False,
            "predictive_edge_proven": False,
            "warning": "Forward statistics are research evidence only; sample size, calibration, costs and multiplicity still matter.",
        }
