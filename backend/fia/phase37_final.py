from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
import json, hashlib

POLICY_PATH = Path(__file__).resolve().parents[1] / "fia_phase37" / "PHASE37_FINAL_FROZEN_POLICY.json"

def load_final_policy() -> Dict[str, Any]:
    data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    data["policy_sha256"] = hashlib.sha256(canonical).hexdigest()
    return data

def final_project_status() -> Dict[str, Any]:
    p = load_final_policy()
    return {
        "ok": True,
        "phase": p["phase"],
        "status": p["status"],
        "project_build_final": p["project_build_final"],
        "further_feature_phases_required": p["further_feature_phases_required"],
        "only_remaining_work_category": p["only_remaining_work_category"],
        "frozen_candidate": {
            "always_include": p["candidate_always_include"],
            "include_groups": p["candidate_include_groups"],
            "exclude_groups": p["candidate_exclude_groups"],
        },
        "safety": {
            "production_weights_changed": p["production_weights_changed"],
            "rl_live_weight": p["rl_live_weight"],
            "broker_execution": p["broker_execution"],
            "fake_accuracy_claims_blocked": p["fake_accuracy_claims_blocked"],
            "probability_claim_requires_oos_validation": p["probability_claim_requires_oos_validation"],
        },
        "licensed_data_policy": {
            "fail_closed_groups": p["licensed_groups_fail_closed"],
            "missing_data_is_unfinished_code": p["missing_licensed_data_is_unfinished_code"],
        },
        "policy_version": p["policy_version"],
        "policy_sha256": p["policy_sha256"],
    }
