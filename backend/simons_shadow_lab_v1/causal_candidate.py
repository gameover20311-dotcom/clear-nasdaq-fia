"""Immutable causal-candidate lifecycle for SIMONS SHADOW LAB V1.

Research-only: never modifies BASE_FIA or production Forward-OOS and never
auto-promotes a candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .causal_features import extract_lock_time_features, state_signature
from .lab import GENESIS, LAB_SCHEMA_VERSION, ShadowLab, _float, _parse_dt, _read_json, _write_new_json, canonical_bytes, sha256_bytes


@dataclass(frozen=True)
class CausalCandidateSpec:
    name: str
    horizon_hours: int
    conditions: Sequence[Mapping[str, Any]]
    predicted_direction: str
    discovery_snapshot_id: str
    discovery_forecast_ids: Sequence[str]
    tests_run_before_selection: int
    experiment_event_hash: str = ""
    notes: str = ""

    def normalized(self) -> Dict[str, Any]:
        if self.horizon_hours not in (4, 8):
            raise ValueError("horizon_hours must be 4 or 8")
        direction = str(self.predicted_direction or "").upper()
        if direction not in {"BULLISH", "BEARISH", "FOLLOW_FIA"}:
            raise ValueError("invalid predicted_direction")
        if int(self.tests_run_before_selection) < 1:
            raise ValueError("tests_run_before_selection must be >= 1")
        allowed = {"eq", "ne", "gte", "lte", "gt", "lt", "in"}
        conditions = []
        for raw in self.conditions:
            field = str(raw.get("field") or "").strip()
            op = str(raw.get("op") or "").strip().lower()
            if not field or op not in allowed:
                raise ValueError("invalid causal candidate condition")
            conditions.append({"field": field, "op": op, "value": raw.get("value")})
        return {
            "name": str(self.name),
            "horizon_hours": int(self.horizon_hours),
            "conditions": conditions,
            "predicted_direction": direction,
            "discovery_snapshot_id": str(self.discovery_snapshot_id),
            "discovery_forecast_ids": sorted(set(str(x) for x in self.discovery_forecast_ids)),
            "tests_run_before_selection": int(self.tests_run_before_selection),
            "experiment_event_hash": str(self.experiment_event_hash or ""),
            "notes": str(self.notes or ""),
        }


def _match(features: Mapping[str, Any], condition: Mapping[str, Any]) -> bool:
    actual, expected = features.get(str(condition.get("field") or "")), condition.get("value")
    op = str(condition.get("op") or "")
    if op == "eq": return actual == expected
    if op == "ne": return actual != expected
    if op == "in": return actual in (expected or [])
    if actual is None or expected is None: return False
    try:
        a, b = float(actual), float(expected)
    except (TypeError, ValueError):
        return False
    if op == "gte": return a >= b
    if op == "lte": return a <= b
    if op == "gt": return a > b
    if op == "lt": return a < b
    return False


class CausalCandidateLab:
    def __init__(self, source_root: Path, lab_root: Path):
        self.source_root = Path(source_root)
        self.lab_root = Path(lab_root)
        self.core = ShadowLab(self.source_root, self.lab_root)

    def freeze(self, spec: CausalCandidateSpec, now: Optional[datetime] = None) -> Dict[str, Any]:
        normalized = spec.normalized()
        manifest, rows = self.core.load_snapshot(normalized["discovery_snapshot_id"])
        known = {str(r.get("forecast_id") or "") for r in rows}
        if not set(normalized["discovery_forecast_ids"]).issubset(known):
            raise ValueError("candidate references IDs outside discovery snapshot")
        now = now or datetime.now(timezone.utc)
        core = {
            "schema_version": LAB_SCHEMA_VERSION,
            "candidate_type": "CAUSAL_LOCK_TIME_FEATURE_CANDIDATE",
            "created_at_utc": now.astimezone(timezone.utc).isoformat(),
            "spec": normalized,
            "discovery_rows_sha256": manifest.get("rows_sha256"),
            "feature_policy": "LOCK_TIME_ONLY_OUTCOMES_FORBIDDEN_AT_DECISION",
            "status": "FORWARD_VALIDATION_READY_NOT_PROVEN",
            "automatic_production_promotion": False,
            "production_modified": False,
        }
        cid = "CCAND-" + sha256_bytes(canonical_bytes(core))[:24]
        payload = {**core, "candidate_id": cid}
        payload["candidate_sha256"] = sha256_bytes(canonical_bytes(payload))
        _write_new_json(self.lab_root / "causal_candidates" / f"{cid}.json", payload)
        return payload

    def load(self, candidate_id: str) -> Dict[str, Any]:
        payload = _read_json(self.lab_root / "causal_candidates" / f"{candidate_id}.json")
        unsigned = dict(payload)
        claimed = str(unsigned.pop("candidate_sha256", ""))
        if claimed != sha256_bytes(canonical_bytes(unsigned)):
            raise RuntimeError("causal candidate hash mismatch")
        return payload

    def _events(self, candidate_id: str) -> List[Dict[str, Any]]:
        root = self.lab_root / "causal_validation" / candidate_id / "events"
        if not root.exists(): return []
        events, prev = [], GENESIS
        for i, path in enumerate(sorted(root.glob("*.json")), 1):
            event = _read_json(path)
            unsigned = dict(event)
            claimed = str(unsigned.pop("event_hash", ""))
            if claimed != sha256_bytes(canonical_bytes(unsigned)):
                raise RuntimeError(f"causal event hash mismatch:{path.name}")
            if int(event.get("seq") or 0) != i or event.get("prev_event_hash") != prev:
                raise RuntimeError("causal validation chain mismatch")
            prev = claimed
            events.append(event)
        return events

    def _append(self, candidate_id: str, event_type: str, forecast_id: str,
                payload: Mapping[str, Any], now: datetime) -> Dict[str, Any]:
        events = self._events(candidate_id)
        if any(e.get("event_type") == event_type and e.get("forecast_id") == forecast_id for e in events):
            raise FileExistsError("immutable causal event already exists")
        seq = len(events) + 1
        unsigned = {
            "schema_version": LAB_SCHEMA_VERSION,
            "seq": seq,
            "event_type": event_type,
            "candidate_id": candidate_id,
            "forecast_id": str(forecast_id),
            "created_at_utc": now.astimezone(timezone.utc).isoformat(),
            "prev_event_hash": events[-1]["event_hash"] if events else GENESIS,
            "payload": dict(payload),
        }
        event = {**unsigned, "event_hash": sha256_bytes(canonical_bytes(unsigned))}
        _write_new_json(self.lab_root / "causal_validation" / candidate_id / "events" / f"{seq:08d}_{event_type.lower()}_{forecast_id}.json", event)
        return event

    def lock_from_row(self, candidate_id: str, row: Mapping[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
        candidate = self.load(candidate_id)
        fid = str(row.get("forecast_id") or "")
        if not fid: raise ValueError("forecast_id required")
        if _parse_dt(row.get("locked_at_utc")) <= _parse_dt(candidate.get("created_at_utc")):
            raise ValueError("forecast is not new after candidate freeze")
        if fid in set(candidate["spec"].get("discovery_forecast_ids") or []):
            raise ValueError("discovery row cannot enter causal validation")
        hours = int(candidate["spec"]["horizon_hours"])
        features = extract_lock_time_features(row, hours)
        fires = all(_match(features, c) for c in candidate["spec"].get("conditions") or [])
        direction = str(candidate["spec"].get("predicted_direction") or "").upper()
        if direction == "FOLLOW_FIA": direction = str(features.get("fia_direction") or "").upper()
        predicted = direction if fires and direction in {"BULLISH", "BEARISH"} else None
        now = now or datetime.now(timezone.utc)
        return self._append(candidate_id, "CAUSAL_DECISION_LOCK", fid, {
            "production_lock_event_hash": row.get("lock_event_hash"),
            "production_locked_at_utc": row.get("locked_at_utc"),
            "horizon_hours": hours,
            "decision": "FIRE" if fires else "NO_FIRE",
            "predicted_direction": predicted,
            "features": features,
            "state_signature": state_signature(features),
            "outcome_information_read": False,
            "production_modified": False,
        }, now)

    def resolve_from_row(self, candidate_id: str, row: Mapping[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
        candidate = self.load(candidate_id)
        fid = str(row.get("forecast_id") or "")
        hours = int(candidate["spec"]["horizon_hours"])
        decision = next((e for e in self._events(candidate_id) if e.get("event_type") == "CAUSAL_DECISION_LOCK" and e.get("forecast_id") == fid), None)
        if decision is None: raise ValueError("decision must be locked before resolution")
        outcome = ((row.get("outcomes") or {}).get(f"{hours}h") or {})
        actual = str(outcome.get("actual_direction") or "").upper()
        if actual not in {"BULLISH", "BEARISH"}: raise ValueError("production outcome not yet resolved")
        predicted = str((decision.get("payload") or {}).get("predicted_direction") or "").upper()
        correct = predicted == actual if predicted in {"BULLISH", "BEARISH"} else None
        entry, future = _float(outcome.get("entry_price")), _float(outcome.get("outcome_price"))
        gross = (future-entry) * (1 if predicted == "BULLISH" else -1) if entry is not None and future is not None and predicted in {"BULLISH", "BEARISH"} else None
        now = now or datetime.now(timezone.utc)
        return self._append(candidate_id, "CAUSAL_DECISION_RESOLUTION", fid, {
            "horizon_hours": hours,
            "decision": (decision.get("payload") or {}).get("decision"),
            "predicted_direction": predicted or None,
            "actual_direction": actual,
            "correct": correct,
            "entry_price": entry,
            "outcome_price": future,
            "gross_points_directional": gross,
            "resolution_event_hash": outcome.get("resolution_event_hash"),
            "resolution_only": True,
            "production_modified": False,
        }, now)

    def report(self, candidate_id: str, assumed_round_trip_cost_points: float = 0.0) -> Dict[str, Any]:
        if assumed_round_trip_cost_points < 0: raise ValueError("assumed cost cannot be negative")
        self.load(candidate_id)
        events = self._events(candidate_id)
        decisions = [e for e in events if e.get("event_type") == "CAUSAL_DECISION_LOCK"]
        fired = [e for e in decisions if (e.get("payload") or {}).get("decision") == "FIRE"]
        resolutions = {e.get("forecast_id"): e for e in events if e.get("event_type") == "CAUSAL_DECISION_RESOLUTION"}
        resolved = [resolutions[e.get("forecast_id")] for e in fired if e.get("forecast_id") in resolutions and (resolutions[e.get("forecast_id")].get("payload") or {}).get("correct") is not None]
        n = len(resolved)
        correct = sum(1 for e in resolved if (e.get("payload") or {}).get("correct") is True)
        gross = [_float((e.get("payload") or {}).get("gross_points_directional")) for e in resolved]
        gross = [x for x in gross if x is not None]
        net = [x-assumed_round_trip_cost_points for x in gross]
        status = "INSUFFICIENT_SAMPLE_NOT_PROVEN" if n < 30 else "FORWARD_VALIDATING_NOT_PROVEN" if n < 50 else "RESEARCH_REVIEW_ELIGIBLE_NOT_PRODUCTION_APPROVED"
        return {
            "schema_version": LAB_SCHEMA_VERSION,
            "candidate_id": candidate_id,
            "candidate_status": status,
            "forward_decisions": len(decisions),
            "fires": len(fired),
            "abstentions": len(decisions)-len(fired),
            "resolved_fires": n,
            "correct": correct,
            "hit_rate": correct/n if n else None,
            "gross_average_points": sum(gross)/len(gross) if gross else None,
            "assumed_round_trip_cost_points": assumed_round_trip_cost_points,
            "net_average_points_after_assumed_friction": sum(net)/len(net) if net else None,
            "friction_is_assumption_not_measured_cost": True,
            "predictive_edge_proven": False,
            "profitability_proven": False,
            "automatic_production_promotion": False,
            "production_modified": False,
        }
