"""Append-only experiment registry for SIMONS SHADOW LAB V2 hybrid."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .lab import GENESIS, _read_json, _write_new_json, canonical_bytes, sha256_bytes


class ExperimentRegistry:
    """Hash-chained log of every registered discovery/robustness experiment.

    V2 stores the declared search family/hash, correction method, origin and
    preregistered acceptance criteria so AI/human/systematic hypotheses all pay
    the same multiplicity and validation cost.
    """
    def __init__(self, lab_root: Path):
        self.root = Path(lab_root) / "experiments" / "events"

    def events(self) -> List[Dict[str, Any]]:
        if not self.root.exists():
            return []
        out: List[Dict[str, Any]] = []
        prev = GENESIS
        for i, path in enumerate(sorted(self.root.glob("*.json")), 1):
            event = _read_json(path)
            unsigned = dict(event)
            claimed = str(unsigned.pop("event_hash", ""))
            if claimed != sha256_bytes(canonical_bytes(unsigned)):
                raise RuntimeError(f"experiment event hash mismatch:{path.name}")
            if int(event.get("seq") or 0) != i or event.get("prev_event_hash") != prev:
                raise RuntimeError("experiment registry chain mismatch")
            prev = claimed
            out.append(event)
        return out

    def append(self, experiment_type: str, snapshot_id: str,
               search_space: Mapping[str, Any], result: Mapping[str, Any],
               *, now: Optional[datetime] = None,
               origin: str = "SYSTEMATIC",
               correction_method: str = "DECLARED_IN_RESULT",
               acceptance_criteria: Optional[Mapping[str, Any]] = None,
               search_family: str = "UNSPECIFIED") -> Dict[str, Any]:
        existing = self.events()
        now = now or datetime.now(timezone.utc)
        seq = len(existing) + 1
        prev = existing[-1]["event_hash"] if existing else GENESIS
        result_hash = sha256_bytes(canonical_bytes(dict(result)))
        search_space_dict = dict(search_space)
        search_hash = sha256_bytes(canonical_bytes(search_space_dict))
        unsigned = {
            "seq": seq,
            "event_type": "EXPERIMENT_REGISTERED",
            "experiment_type": str(experiment_type),
            "search_family": str(search_family),
            "origin": str(origin).upper(),
            "snapshot_id": str(snapshot_id),
            "created_at_utc": now.astimezone(timezone.utc).isoformat(),
            "search_space": search_space_dict,
            "search_space_sha256": search_hash,
            "correction_method": str(correction_method),
            "preregistered_acceptance_criteria": dict(acceptance_criteria or {}),
            "result_sha256": result_hash,
            "code_version": "SIMONS_SHADOW_LAB_V2_HYBRID",
            "prev_event_hash": prev,
            "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
            "production_modified": False,
        }
        event = {**unsigned, "event_hash": sha256_bytes(canonical_bytes(unsigned))}
        _write_new_json(self.root / f"{seq:08d}_{result_hash[:16]}.json", event)
        return event

    def audit(self) -> Dict[str, Any]:
        events = self.events()
        return {
            "ok": True,
            "experiments_registered": len(events),
            "head_event_hash": events[-1]["event_hash"] if events else GENESIS,
            "append_only": True,
            "all_search_spaces_hashed": all(bool(e.get("search_space_sha256")) for e in events),
            "production_modified": False,
        }
