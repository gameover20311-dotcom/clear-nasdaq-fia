"""Append-only experiment registry for SIMONS SHADOW LAB V1."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .lab import GENESIS, _read_json, _write_new_json, canonical_bytes, sha256_bytes


class ExperimentRegistry:
    """Hash-chained log of every registered discovery/robustness experiment."""
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
               *, now: Optional[datetime] = None) -> Dict[str, Any]:
        existing = self.events()
        now = now or datetime.now(timezone.utc)
        seq = len(existing) + 1
        prev = existing[-1]["event_hash"] if existing else GENESIS
        result_hash = sha256_bytes(canonical_bytes(dict(result)))
        unsigned = {
            "seq": seq,
            "event_type": "EXPERIMENT_REGISTERED",
            "experiment_type": str(experiment_type),
            "snapshot_id": str(snapshot_id),
            "created_at_utc": now.astimezone(timezone.utc).isoformat(),
            "search_space": dict(search_space),
            "result_sha256": result_hash,
            "code_version": "SIMONS_SHADOW_LAB_V1",
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
            "production_modified": False,
        }
