"""SIMONS SHADOW LAB V1 — isolated, read-only Forward-OOS research.

Scientific rules:
- never write to fia_forward_oos;
- never import production FIA code that may restore/append/reseal data;
- lock-time features and later outcomes remain separate;
- 4H and 8H stay separate;
- discovery rows never validate their own candidate;
- candidate retuning requires a new identity/version;
- multiple-testing burden is explicit;
- no automatic production promotion;
- PREDICTIVE_EDGE remains NOT_PROVEN.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

LAB_SCHEMA = "SIMONS_SHADOW_LAB_V1"
PREDICTIVE_EDGE_STATUS = "NOT_PROVEN"
SUPPORTED_HORIZONS = ("4h", "8h")
MIN_DISCOVERY_ROWS = 30
MIN_RULE_FIRES = 12
DEFAULT_VALIDATION_N = 30


class IntegrityError(RuntimeError):
    pass


class CandidateError(RuntimeError):
    pass


def _primitive(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, bool)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).isoformat()
    if isinstance(v, Path):
        return str(v)
    if isinstance(v, Mapping):
        return {str(k): _primitive(x) for k, x in sorted(v.items(), key=lambda x: str(x[0]))}
    if isinstance(v, (list, tuple, set)):
        return [_primitive(x) for x in v]
    return str(v)


def canonical_bytes(v: Any) -> bytes:
    return json.dumps(_primitive(v), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise IntegrityError(f"Expected JSON object: {path}")
    return value


def _dt(v: Any) -> datetime:
    s = str(v or "").strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if not s:
        raise ValueError("timestamp missing")
    out = datetime.fromisoformat(s)
    if out.tzinfo is None:
        out = out.replace(tzinfo=timezone.utc)
    return out.astimezone(timezone.utc)


def _float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def verify_campaign_seal_readonly(backend_root: Path | str, forward_root: Path | str) -> Dict[str, Any]:
    backend_root, forward_root = Path(backend_root), Path(forward_root)
    path = forward_root / "FORWARD_OOS_CAMPAIGN_SEAL.json"
    if not path.is_file():
        return {"ok": False, "reason": "CAMPAIGN_SEAL_MISSING", "path": str(path)}
    try:
        payload = _read_json(path)
        unsigned = dict(payload)
        claimed = str(unsigned.pop("seal_hash", ""))
        seal_ok = claimed == sha256_bytes(canonical_bytes(unsigned))
        fp = payload.get("model_fingerprint") or {}
        sealed_files = fp.get("files") or {}
        current, mismatches = {}, []
        for rel, expected in sorted(sealed_files.items()):
            p = backend_root / str(rel)
            actual = sha256_file(p) if p.is_file() else "MISSING"
            current[str(rel)] = actual
            if actual != expected:
                mismatches.append(str(rel))
        current_digest = sha256_bytes(canonical_bytes(current))
        expected_digest = str(fp.get("digest") or "")
        fingerprint_ok = not mismatches and current_digest == expected_digest
        return {
            "ok": seal_ok and fingerprint_ok,
            "seal_hash_valid": seal_ok,
            "model_fingerprint_match": fingerprint_ok,
            "campaign_id": payload.get("campaign_id"),
            "sealed_at_utc": payload.get("sealed_at_utc"),
            "seal_hash": claimed,
            "sealed_model_fingerprint_digest": expected_digest,
            "current_model_fingerprint_digest": current_digest,
            "mismatched_files": mismatches,
            "read_only": True,
        }
    except Exception as exc:
        return {"ok": False, "reason": f"CAMPAIGN_SEAL_UNREADABLE:{type(exc).__name__}:{exc}", "path": str(path)}


def verify_ledger_readonly(forward_root: Path | str) -> Dict[str, Any]:
    root = Path(forward_root)
    events_dir = root / "events"
    files = sorted(events_dir.glob("*.json")) if events_dir.is_dir() else []
    issues: List[str] = []
    prev, expected_seq = "GENESIS", 1
    locks: set[str] = set()
    resolved: set[Tuple[str, str]] = set()
    lock_count = resolution_count = abstention_count = 0
    for path in files:
        try:
            event = _read_json(path)
        except Exception as exc:
            issues.append(f"unreadable:{path.name}:{exc}")
            continue
        seq = event.get("seq")
        if seq != expected_seq:
            issues.append(f"sequence:{path.name}")
        if event.get("prev_event_hash") != prev:
            issues.append(f"chain_prev:{path.name}")
        unsigned = dict(event)
        claimed = str(unsigned.pop("event_hash", ""))
        if claimed != sha256_bytes(canonical_bytes(unsigned)):
            issues.append(f"event_hash:{path.name}")
        et, fid = str(event.get("event_type") or ""), str(event.get("forecast_id") or "")
        if et == "FORECAST_LOCK":
            lock_count += 1
            if not fid or fid in locks:
                issues.append(f"duplicate_lock:{fid}")
            locks.add(fid)
            meta = (event.get("payload") or {}).get("evidence") or {}
            rel, digest = str(meta.get("path") or ""), str(meta.get("sha256") or "")
            if not rel or not digest:
                issues.append(f"missing_evidence_ref:{fid}")
            else:
                ep = root / rel
                try:
                    ep.resolve().relative_to(root.resolve())
                except Exception:
                    issues.append(f"evidence_path_escape:{fid}")
                if not ep.is_file():
                    issues.append(f"missing_evidence:{fid}")
                elif sha256_file(ep) != digest:
                    issues.append(f"evidence_hash:{fid}")
        elif et in {"RESOLUTION_4H", "RESOLUTION_8H"}:
            resolution_count += 1
            key = (fid, et)
            if fid not in locks:
                issues.append(f"resolution_without_lock:{fid}:{et}")
            if key in resolved:
                issues.append(f"duplicate_resolution:{fid}:{et}")
            resolved.add(key)
        elif et == "ABSTENTION_OBSERVATION":
            abstention_count += 1
        prev, expected_seq = claimed, expected_seq + 1
    head = root / "LEDGER_HEAD.json"
    if files:
        if not head.is_file():
            issues.append("missing_ledger_head")
        else:
            try:
                h = _read_json(head)
                u = dict(h)
                anchor = str(u.pop("anchor_hash", ""))
                if anchor != sha256_bytes(canonical_bytes(u)):
                    issues.append("ledger_head_anchor_hash")
                if int(h.get("events", -1)) != len(files):
                    issues.append("ledger_head_event_count")
                if str(h.get("head_event_hash") or "") != prev:
                    issues.append("ledger_head_event_hash")
            except Exception as exc:
                issues.append(f"unreadable_ledger_head:{exc}")
    return {
        "ok": not issues, "events": len(files), "forecast_locks": lock_count,
        "resolution_events": resolution_count, "abstention_events": abstention_count,
        "head_event_hash": prev, "issues": issues, "read_only": True,
    }


def audit_source(backend_root: Path | str, forward_root: Path | str) -> Dict[str, Any]:
    seal = verify_campaign_seal_readonly(backend_root, forward_root)
    ledger = verify_ledger_readonly(forward_root)
    return {
        "ok": bool(seal.get("ok")) and bool(ledger.get("ok")),
        "schema": LAB_SCHEMA, "predictive_edge": PREDICTIVE_EDGE_STATUS,
        "campaign_seal": seal, "ledger": ledger, "production_mutation_allowed": False,
    }


def _horizon(base: Mapping[str, Any], h: str) -> Dict[str, Any]:
    cell = ((base.get("horizon_probabilities") or {}).get(h) or {})
    bull = _float(cell.get("bullish_probability"))
    bear = _float(cell.get("bearish_probability"))
    return {
        "bullish_probability": bull if bull is not None else _float(base.get("bullish_probability")),
        "bearish_probability": bear if bear is not None else _float(base.get("bearish_probability")),
        "direction": str(cell.get("direction") or base.get("direction") or "").upper(),
        "state": str(cell.get("state") or "").upper(),
        "confidence": _float(cell.get("confidence")) if cell.get("confidence") is not None else _float(base.get("confidence")),
        "actionable": bool(cell.get("actionable")) if "actionable" in cell else None,
        "source": cell.get("source"),
    }


def _features(lock: Mapping[str, Any], evidence: Mapping[str, Any]) -> Dict[str, Any]:
    p = lock.get("payload") or {}
    base = ((p.get("models") or {}).get("BASE_FIA") or {})
    locked_at = str(p.get("locked_at_utc") or lock.get("created_at_utc") or "")
    lock_dt = _dt(locked_at)
    if base.get("generated_at") and _dt(base.get("generated_at")) > lock_dt:
        raise IntegrityError(f"future_generated_at:{lock.get('forecast_id')}")
    if evidence.get("captured_at_utc") and _dt(evidence.get("captured_at_utc")) > lock_dt:
        raise IntegrityError(f"future_evidence_capture:{lock.get('forecast_id')}")
    h4, h8 = _horizon(base, "4h"), _horizon(base, "8h")
    p4, p8 = h4.get("bullish_probability"), h8.get("bullish_probability")
    return {
        "forecast_id": str(lock.get("forecast_id") or ""), "locked_at_utc": locked_at,
        "checkpoint_date_et": p.get("checkpoint_date_et"),
        "campaign_id": (p.get("campaign") or {}).get("campaign_id"),
        "evidence_sha256": (p.get("evidence") or {}).get("sha256"),
        "model_fingerprint_digest": (p.get("model_fingerprint") or {}).get("digest"),
        "regime": str(base.get("regime") or "UNKNOWN").upper(),
        "base_direction": str(base.get("direction") or "").upper(),
        "base_confidence": _float(base.get("confidence")),
        "data_coverage": _float(base.get("data_coverage")),
        "intelligence_coverage": _float(base.get("intelligence_coverage")),
        "status": str(base.get("status") or "").upper(),
        "horizons": {"4h": h4, "8h": h8},
        "horizon_agreement": bool(h4.get("direction") and h4.get("direction") == h8.get("direction")),
        "probability_divergence_abs": round(abs(float(p4) - float(p8)), 6) if p4 is not None and p8 is not None else None,
        "entry_contract": (p.get("entry") or {}).get("contract"),
        "evidence_available_at_or_before_lock": True,
    }


def _outcome(event: Mapping[str, Any]) -> Dict[str, Any]:
    p = event.get("payload") or {}
    entry, future = _float(p.get("entry_price")), _float(p.get("outcome_price"))
    ret = None if entry in (None, 0.0) or future is None else (future - entry) / entry
    return {
        "horizon_hours": int(p.get("horizon_hours") or (4 if event.get("event_type") == "RESOLUTION_4H" else 8)),
        "target_utc": p.get("target_utc"), "resolved_at_utc": p.get("resolved_at_utc"),
        "actual_direction": str(p.get("actual_direction") or "").upper(),
        "entry_price": entry, "outcome_price": future, "return_fraction": ret,
        "resolution_event_hash": event.get("event_hash"),
    }


def _rows(forward_root: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    events_dir = forward_root / "events"
    events = [_read_json(p) for p in sorted(events_dir.glob("*.json"))] if events_dir.is_dir() else []
    locks: Dict[str, Dict[str, Any]] = {}
    resolutions: Dict[str, Dict[str, Dict[str, Any]]] = {}
    abstentions: List[Dict[str, Any]] = []
    for e in events:
        et, fid = e.get("event_type"), str(e.get("forecast_id") or "")
        if et == "FORECAST_LOCK":
            locks[fid] = e
        elif et in {"RESOLUTION_4H", "RESOLUTION_8H"}:
            resolutions.setdefault(fid, {})["4h" if et == "RESOLUTION_4H" else "8h"] = e
        elif et == "ABSTENTION_OBSERVATION":
            abstentions.append({"forecast_id": fid, "payload": _primitive(e.get("payload") or {})})
    out = []
    for fid, lock in locks.items():
        meta = (lock.get("payload") or {}).get("evidence") or {}
        evidence = _read_json(forward_root / str(meta.get("path") or ""))
        out.append({
            "forecast_id": fid,
            "features": _features(lock, evidence),
            "outcomes": {h: _outcome(e) for h, e in (resolutions.get(fid) or {}).items()},
        })
    out.sort(key=lambda r: str(r["features"].get("locked_at_utc") or ""))
    return out, abstentions


def build_snapshot(backend_root: Path | str, forward_root: Path | str, lab_root: Path | str,
                   *, created_at: Optional[datetime] = None) -> Dict[str, Any]:
    backend_root, forward_root, lab_root = Path(backend_root), Path(forward_root), Path(lab_root)
    audit = audit_source(backend_root, forward_root)
    if not audit["ok"]:
        raise IntegrityError("source audit failed; refusing snapshot")
    rows, abstentions = _rows(forward_root)
    payload = {
        "schema": LAB_SCHEMA, "campaign_id": audit["campaign_seal"].get("campaign_id"),
        "campaign_seal_hash": audit["campaign_seal"].get("seal_hash"),
        "source_head_event_hash": audit["ledger"].get("head_event_hash"),
        "rows": rows, "abstentions": abstentions, "predictive_edge": PREDICTIVE_EDGE_STATUS,
    }
    data = canonical_bytes(payload) + b"\n"
    digest, snapshot_id = sha256_bytes(data), f"SSLV1-{sha256_bytes(data)[:16]}"
    root = lab_root / "snapshots"
    root.mkdir(parents=True, exist_ok=True)
    data_path, manifest_path = root / f"{snapshot_id}.json", root / f"{snapshot_id}.manifest.json"
    if data_path.exists() and sha256_file(data_path) != digest:
        raise IntegrityError("snapshot id collision")
    if not data_path.exists():
        fd = os.open(data_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
    manifest = {
        "schema": LAB_SCHEMA, "snapshot_id": snapshot_id, "snapshot_sha256": digest,
        "created_at_utc": (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "campaign_id": payload.get("campaign_id"), "source_head_event_hash": payload.get("source_head_event_hash"),
        "eligible_directional_rows": len(rows), "abstention_rows": len(abstentions),
        "fully_resolved_rows": sum(1 for r in rows if all(h in r["outcomes"] for h in SUPPORTED_HORIZONS)),
        "feature_policy": "LOCK_TIME_ONLY", "outcomes_separate_from_features": True,
        "horizons_separate": True, "production_mutation_allowed": False,
        "predictive_edge": PREDICTIVE_EDGE_STATUS,
    }
    if manifest_path.exists():
        old = _read_json(manifest_path)
        if old.get("snapshot_sha256") != digest:
            raise IntegrityError("snapshot manifest mismatch")
        manifest = old
    else:
        fd = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(fd, "wb") as f:
            f.write(canonical_bytes(manifest) + b"\n"); f.flush(); os.fsync(f.fileno())
    return {"ok": True, "snapshot": manifest, "data_path": str(data_path), "manifest_path": str(manifest_path)}


def load_snapshot(path: Path | str) -> Dict[str, Any]:
    value = _read_json(Path(path))
    if value.get("schema") != LAB_SCHEMA:
        raise IntegrityError("wrong snapshot schema")
    return value


def benjamini_hochberg(pvalues: Sequence[float]) -> List[float]:
    m = len(pvalues)
    if not m:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    out, running = [1.0] * m, 1.0
    for pos in range(m - 1, -1, -1):
        idx, rank = order[pos], pos + 1
        running = min(running, min(1.0, float(pvalues[idx]) * m / rank))
        out[idx] = running
    return out


def _binomial_p(k: int, n: int) -> float:
    if n <= 0:
        return 1.0
    probs = [math.comb(n, i) * (0.5 ** n) for i in range(n + 1)]
    obs = probs[k]
    return min(1.0, sum(x for x in probs if x <= obs + 1e-15))


def _actual(o: Mapping[str, Any]) -> Optional[int]:
    a = str(o.get("actual_direction") or "").upper()
    return 1 if a == "BULLISH" else 0 if a == "BEARISH" else None


def _direction(rule: Mapping[str, Any]) -> str:
    return str(rule.get("direction") or "").upper()


def _fires(f: Mapping[str, Any], rule: Mapping[str, Any]) -> bool:
    h = str(rule.get("horizon") or "").lower()
    if h not in SUPPORTED_HORIZONS:
        return False
    cell = ((f.get("horizons") or {}).get(h) or {})
    bull, conf = _float(cell.get("bullish_probability")), _float(cell.get("confidence"))
    if bull is None:
        return False
    lo, hi, min_conf = _float(rule.get("min_bullish_probability")), _float(rule.get("max_bullish_probability")), _float(rule.get("min_confidence"))
    if lo is not None and bull < lo:
        return False
    if hi is not None and bull > hi:
        return False
    if min_conf is not None and (conf is None or conf < min_conf):
        return False
    if rule.get("require_horizon_agreement") and not f.get("horizon_agreement"):
        return False
    return True


def _eval(rows: Sequence[Mapping[str, Any]], rule: Mapping[str, Any]) -> Dict[str, Any]:
    h, d = str(rule.get("horizon") or "").lower(), _direction(rule)
    fires = correct = 0
    returns, ids = [], []
    for row in rows:
        f, o = row.get("features") or {}, (row.get("outcomes") or {}).get(h)
        if not isinstance(o, Mapping) or not _fires(f, rule):
            continue
        y = _actual(o)
        if y is None:
            continue
        fires += 1
        ids.append(str(row.get("forecast_id") or ""))
        pred = 1 if d == "BULLISH" else 0
        correct += int(pred == y)
        r = _float(o.get("return_fraction"))
        if r is not None:
            returns.append(r if d == "BULLISH" else -r)
    return {
        "fires": fires, "correct": correct, "accuracy": correct / fires if fires else None,
        "mean_directional_return_fraction": statistics.mean(returns) if returns else None,
        "p_value_vs_50pct": _binomial_p(correct, fires) if fires else 1.0,
        "forecast_ids": ids,
    }


def discover_threshold_candidates(snapshot: Mapping[str, Any], *, min_rows: int = MIN_DISCOVERY_ROWS,
                                  min_fires: int = MIN_RULE_FIRES, max_hypotheses: int = 96) -> Dict[str, Any]:
    rows = [r for r in (snapshot.get("rows") or []) if all(h in (r.get("outcomes") or {}) for h in SUPPORTED_HORIZONS)]
    if len(rows) < min_rows:
        return {"status": "INSUFFICIENT_SAMPLE", "eligible_rows": len(rows), "minimum_rows": min_rows,
                "hypotheses_tested": 0, "candidates": [], "predictive_edge": PREDICTIVE_EDGE_STATUS}
    rules = []
    for h in SUPPORTED_HORIZONS:
        for p in (52.5, 55.0, 57.5, 60.0):
            for c in (None, 25.0, 40.0):
                for agree in (False, True):
                    rules += [
                        {"horizon": h, "direction": "BULLISH", "min_bullish_probability": p, "max_bullish_probability": None, "min_confidence": c, "require_horizon_agreement": agree},
                        {"horizon": h, "direction": "BEARISH", "min_bullish_probability": None, "max_bullish_probability": 100.0-p, "min_confidence": c, "require_horizon_agreement": agree},
                    ]
    tested, pvals = [], []
    for i, rule in enumerate(rules[:max_hypotheses], 1):
        metrics = _eval(rows, rule)
        tested.append({"hypothesis_id": f"H{i:03d}", "rule": rule, "metrics": metrics})
        pvals.append(metrics["p_value_vs_50pct"])
    for item, q in zip(tested, benjamini_hochberg(pvals)):
        item["q_value_bh"] = q
        item["discovery_eligible"] = item["metrics"]["fires"] >= min_fires and q <= 0.10
        item["status"] = "DISCOVERY_ONLY" if item["discovery_eligible"] else "REJECTED_AT_DISCOVERY"
    candidates = sorted((x for x in tested if x["discovery_eligible"]), key=lambda x: (x["q_value_bh"], -x["metrics"]["fires"]))
    return {
        "status": "DISCOVERY_COMPLETE", "eligible_rows": len(rows), "hypotheses_tested": len(tested),
        "multiple_testing": "BENJAMINI_HOCHBERG", "fdr_threshold": 0.10,
        "all_hypotheses": tested, "candidates": candidates,
        "warning": "Discovery performance is not validation. Freeze before future unseen testing.",
        "predictive_edge": PREDICTIVE_EDGE_STATUS,
    }


def _verify_candidate(candidate: Mapping[str, Any]) -> None:
    u = dict(candidate)
    claimed = str(u.pop("freeze_hash", ""))
    if not claimed or claimed != sha256_bytes(canonical_bytes(u)):
        raise CandidateError("candidate freeze hash invalid")
    if candidate.get("state") != "FROZEN":
        raise CandidateError("candidate not frozen")


def freeze_candidate(lab_root: Path | str, *, candidate_id: str, rule: Mapping[str, Any],
                     discovery_snapshot_id: str, discovery_snapshot_sha256: str,
                     discovery_forecast_ids: Sequence[str], created_at: Optional[datetime] = None,
                     minimum_validation_n: int = DEFAULT_VALIDATION_N) -> Dict[str, Any]:
    root = Path(lab_root) / "candidates"
    root.mkdir(parents=True, exist_ok=True)
    candidate_id = str(candidate_id or "").strip()
    if not candidate_id or any(x in candidate_id for x in ("/", "\\", "..")):
        raise CandidateError("unsafe candidate_id")
    if str(rule.get("horizon") or "").lower() not in SUPPORTED_HORIZONS or _direction(rule) not in {"BULLISH", "BEARISH"}:
        raise CandidateError("invalid horizon/direction")
    path = root / f"{candidate_id}.json"
    contract = {
        "rule": _primitive(rule), "discovery_snapshot_id": discovery_snapshot_id,
        "discovery_snapshot_sha256": discovery_snapshot_sha256,
        "discovery_forecast_ids": sorted(set(str(x) for x in discovery_forecast_ids)),
        "minimum_validation_n": int(minimum_validation_n),
    }
    if path.exists():
        old = _read_json(path)
        if {k: old.get(k) for k in contract} == contract:
            _verify_candidate(old)
            return old
        raise CandidateError("candidate already frozen with different content; use new id/version")
    unsigned = {
        "schema": LAB_SCHEMA, "candidate_id": candidate_id, "version": 1, "state": "FROZEN",
        "frozen_at_utc": (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        **contract,
        "validation_policy": "ONLY_ROWS_LOCKED_AFTER_FREEZE_AND_NOT_IN_DISCOVERY_SET",
        "retuning_policy": "NEW_CANDIDATE_ID_OR_VERSION_REQUIRED",
        "automatic_production_promotion": False, "predictive_edge": PREDICTIVE_EDGE_STATUS,
    }
    payload = dict(unsigned)
    payload["freeze_hash"] = sha256_bytes(canonical_bytes(unsigned))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    with os.fdopen(fd, "wb") as f:
        f.write(canonical_bytes(payload)+b"\n"); f.flush(); os.fsync(f.fileno())
    return payload


def _bootstrap_ci(pairs: Sequence[Tuple[int, int]], seed: str, reps: int = 2000) -> Optional[List[float]]:
    if len(pairs) < 2:
        return None
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    n, vals = len(pairs), []
    for _ in range(reps):
        s = [pairs[rng.randrange(n)] for _ in range(n)]
        vals.append(sum(c-b for c, b in s)/n)
    vals.sort()
    return [vals[int(.025*(reps-1))], vals[int(.975*(reps-1))]]


def validate_candidate(candidate: Mapping[str, Any], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    _verify_candidate(candidate)
    rule, freeze = candidate.get("rule") or {}, _dt(candidate.get("frozen_at_utc"))
    h = str(rule.get("horizon") or "").lower()
    used = set(str(x) for x in (candidate.get("discovery_forecast_ids") or []))
    eligible = []
    for row in snapshot.get("rows") or []:
        if str(row.get("forecast_id") or "") in used:
            continue
        if _dt((row.get("features") or {}).get("locked_at_utc")) <= freeze:
            continue
        if h in (row.get("outcomes") or {}):
            eligible.append(row)
    metrics = _eval(eligible, rule)
    pairs = []
    for row in eligible:
        f, o = row.get("features") or {}, (row.get("outcomes") or {}).get(h) or {}
        if not _fires(f, rule):
            continue
        y = _actual(o)
        bd = str((((f.get("horizons") or {}).get(h) or {}).get("direction") or f.get("base_direction") or "")).upper()
        if y is None or bd not in {"BULLISH", "BEARISH"}:
            continue
        pairs.append((int((1 if _direction(rule)=="BULLISH" else 0)==y), int((1 if bd=="BULLISH" else 0)==y)))
    cand_acc = statistics.mean(c for c, _ in pairs) if pairs else None
    base_acc = statistics.mean(b for _, b in pairs) if pairs else None
    delta = None if cand_acc is None or base_acc is None else cand_acc-base_acc
    ci = _bootstrap_ci(pairs, str(candidate.get("freeze_hash")))
    min_n = int(candidate.get("minimum_validation_n") or DEFAULT_VALIDATION_N)
    if metrics["fires"] < min_n:
        state, verdict = "FORWARD_VALIDATING", "INSUFFICIENT_UNSEEN_SAMPLE"
    else:
        survived = bool(delta is not None and ci is not None and ci[0] > 0)
        state = "ROBUST_CANDIDATE" if survived else "REJECTED"
        verdict = "RESEARCH_PROMOTION_REVIEW_ELIGIBLE" if survived else "VALIDATION_DID_NOT_SURVIVE"
    return {
        "schema": LAB_SCHEMA, "candidate_id": candidate.get("candidate_id"), "candidate_freeze_hash": candidate.get("freeze_hash"),
        "horizon": h, "eligible_future_rows": len(eligible), "candidate_metrics": metrics,
        "paired_base_comparison": {"n": len(pairs), "candidate_accuracy": cand_acc, "base_accuracy": base_acc,
                                   "accuracy_delta_candidate_minus_base": delta, "bootstrap_95_ci_delta": ci},
        "minimum_validation_n": min_n, "state": state, "verdict": verdict,
        "automatic_production_promotion": False, "predictive_edge": PREDICTIVE_EDGE_STATUS,
    }
