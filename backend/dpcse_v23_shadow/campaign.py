from __future__ import annotations

from typing import Any, Dict
import hashlib
import json
import re
from .candidate import CandidateIdentity
from .spec import BASE_IDENTITIES, CAMPAIGN_ID, CONFIRMATORY, HISTORICAL_BACKFILL, PILOT_ALPHA, PILOT_N_TARGET, PREDICTIVE_EDGE, PRIMARY_HORIZON, PROMOTION_ELIGIBLE, REPAIR_BASE_COMMIT, SPEC_HASH

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

def bootstrap_manifest() -> Dict[str, Any]:
    return {"schema": "CLEAR_NASDAQ_DPCSE_V23_SHADOW_BOOTSTRAP_V1", "campaign_id": CAMPAIGN_ID, "status": "NOT_ARMED", "reason": "CANDIDATE_MODEL_NOT_FROZEN", "repair_base_commit": REPAIR_BASE_COMMIT, "base_identities": dict(BASE_IDENTITIES), "dpcse_spec_hash": SPEC_HASH, "primary_horizon": PRIMARY_HORIZON, "pilot_n_target": PILOT_N_TARGET, "pilot_alpha": PILOT_ALPHA, "confirmatory": CONFIRMATORY, "promotion_eligible": PROMOTION_ELIGIBLE, "predictive_edge": PREDICTIVE_EDGE, "historical_backfill": HISTORICAL_BACKFILL, "candidate_model": None, "locked_rows": 0, "resolved_rows": 0}

def build_armed_seal(*, candidate: CandidateIdentity, registered_at_utc: str) -> Dict[str, Any]:
    if not registered_at_utc.strip().endswith(("+00:00", "Z")):
        raise ValueError("registered_at_utc must be explicit UTC")
    unsigned = {"schema": "CLEAR_NASDAQ_DPCSE_V23_SHADOW_SEAL_V1", "campaign_id": CAMPAIGN_ID, "status": "ARMED_N0", "registered_at_utc": registered_at_utc, "repair_base_commit": REPAIR_BASE_COMMIT, "base_identities": dict(BASE_IDENTITIES), "dpcse_spec_hash": SPEC_HASH, "primary_horizon": PRIMARY_HORIZON, "pilot_n_target": PILOT_N_TARGET, "pilot_alpha": PILOT_ALPHA, "confirmatory": CONFIRMATORY, "promotion_eligible": PROMOTION_ELIGIBLE, "predictive_edge": PREDICTIVE_EDGE, "historical_backfill": HISTORICAL_BACKFILL, "candidate_model": {"model_id": candidate.model_id, "model_fingerprint": candidate.model_fingerprint, "predictive_state_schema_hash": candidate.predictive_state_schema_hash}, "locked_rows_at_seal": 0, "resolved_rows_at_seal": 0}
    return {**unsigned, "seal_hash": hashlib.sha256(_canonical(unsigned)).hexdigest()}

def verify_armed_seal(seal: Dict[str, Any]) -> bool:
    if not isinstance(seal, dict) or seal.get("status") != "ARMED_N0": return False
    candidate = seal.get("candidate_model") or {}
    if not all(_SHA256.fullmatch(str(candidate.get(k) or "")) for k in ("model_fingerprint", "predictive_state_schema_hash")): return False
    if seal.get("dpcse_spec_hash") != SPEC_HASH or seal.get("repair_base_commit") != REPAIR_BASE_COMMIT: return False
    if seal.get("locked_rows_at_seal") != 0 or seal.get("resolved_rows_at_seal") != 0: return False
    unsigned = dict(seal); claimed = str(unsigned.pop("seal_hash", ""))
    return claimed == hashlib.sha256(_canonical(unsigned)).hexdigest()
