from __future__ import annotations

"""Frozen protocol constants for the DPCSE V2.3 zero-alpha shadow pilot.

This is a protocol kernel, not a trained predictive model. The V2.3 freeze
defined the gating/bookkeeping contract but did not freeze an exact predictive
state vector or trained Direct-8H law. The campaign therefore stays NOT_ARMED
until a separate candidate model artifact is frozen and fingerprinted.
"""

import hashlib
import json
from typing import Any, Dict

SPEC_VERSION = "DPCSE_V2_3"
CAMPAIGN_ID = "CLEAR_NASDAQ_DPCSE_V23_SHADOW_PILOT"
PRIMARY_HORIZON = "8H"
PILOT_N_TARGET = 50
PILOT_ALPHA = 0.0
ENV_ARM_MIN_RESOLVED = 30
ENV_REFERENCE_WINDOW = 20
ENV_CURRENT_WINDOW = 10
ENV_MAX_STALENESS_CHECKPOINTS = 1
ENV_CURRENT_ERROR_MIN_FOR_RELATIVE_ALARM = 0.70
ENV_ERROR_RATE_INCREASE_STRICTLY_GREATER_THAN = 0.30
DIRECTIONAL_MARGIN_MIN = 0.10
CONFIRMATORY = False
PROMOTION_ELIGIBLE = False
PREDICTIVE_EDGE = "NOT_PROVEN"
HISTORICAL_BACKFILL = "FORBIDDEN"
SEQUENTIAL_E_PROCESS = "DEFERRED"
TRANSITION_GENERATOR = "DEFERRED"
FIRST_PASSAGE_COMMITTOR = "DEFERRED"
H4_PROMOTION = "DEFERRED"
REPAIR_BASE_COMMIT = "14e2a60b7c2fd0b58a8dcba3be263129eae1d482"
BASE_IDENTITIES = {
    "model": "ee7ede6c0db89266e2383baf3bdb87775251df80323bea4c3bea756a186d8eee",
    "protocol": "d0b52e47ec576784ce3f42c9e02f187eb094a4ee23af3ffa37e26f82a03e42ce",
    "infrastructure": "4a114cf7b9b3df738a83b2986c1d4ccb1cfd8c05f7e3fc248248dc9aa7f294a1",
    "classification_manifest": "1e847b0588b21dc2d361e68f33d8009df4e7647efb340af36885da47ffcabca5",
}
FROZEN_SPEC: Dict[str, Any] = {
    "schema": "CLEAR_NASDAQ_DPCSE_V23_SPEC_V1",
    "version": SPEC_VERSION,
    "campaign_id": CAMPAIGN_ID,
    "architecture": ["AVAILABILITY_INTEGRITY", "ENVIRONMENT", "MINIMAL_PREDICTIVE_STATE", "DIRECT_8H_LAW", "HARD_GATES", "BULL_BEAR_NO_EDGE"],
    "binary_law": {"classes": ["BULL", "BEAR"], "sum_to_one": True, "neutral_probability": False, "no_edge_is_decision_not_outcome": True},
    "pilot": {"n_target": PILOT_N_TARGET, "alpha": PILOT_ALPHA, "confirmatory": CONFIRMATORY, "promotion_eligible": PROMOTION_ELIGIBLE, "predictive_edge": PREDICTIVE_EDGE, "primary_horizon": PRIMARY_HORIZON, "historical_backfill": HISTORICAL_BACKFILL},
    "environment": {"arm_min_resolved": ENV_ARM_MIN_RESOLVED, "reference_window": ENV_REFERENCE_WINDOW, "current_window": ENV_CURRENT_WINDOW, "max_staleness_checkpoints": ENV_MAX_STALENESS_CHECKPOINTS, "current_error_min": ENV_CURRENT_ERROR_MIN_FOR_RELATIVE_ALARM, "increase_strictly_greater_than": ENV_ERROR_RATE_INCREASE_STRICTLY_GREATER_THAN, "integer_alarm": "c>=7 AND 2*c-r>=7", "states": ["WARMUP", "VALID", "SHIFT_DETECTED", "STALE"]},
    "directional_gate": {"margin_min": DIRECTIONAL_MARGIN_MIN, "definition": "abs(p_bull-p_bear)", "equivalent_max_probability_min": 0.55, "below_threshold": "NO_EDGE_AMBIGUOUS"},
    "evaluation": {"all_integrity_eligible_probability_rows_in_primary_brier": True, "no_edge_rows_excluded_from_primary_brier": False, "selective_analysis_is_separate": True},
    "deferred": [SEQUENTIAL_E_PROCESS, TRANSITION_GENERATOR, FIRST_PASSAGE_COMMITTOR, H4_PROMOTION],
    "candidate_model_contract": {"exact_predictive_state_frozen_here": False, "trained_direct_8h_law_frozen_here": False, "must_fail_closed_until_frozen": True},
}

def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

SPEC_HASH = hashlib.sha256(canonical_bytes(FROZEN_SPEC)).hexdigest()
