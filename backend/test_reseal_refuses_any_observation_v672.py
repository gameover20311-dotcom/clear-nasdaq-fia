"""Regression: re-seal must refuse ANY existing Forward-OOS ledger event.

An abstention observation is scientifically real even though it is not a
forecast-lock file. The old implementation counted only forecast locks and could
therefore re-pin a campaign after an abstention had already been observed.
"""
from __future__ import annotations

import reseal_forward_oos_campaign as r

before = r.SEAL.read_bytes()
orig_verify = r.verify_campaign_seal
orig_events = r.existing_events
orig_locks = r.existing_locks

try:
    r.verify_campaign_seal = lambda: {
        "ok": False,
        "campaign_id": "TEST-CAMPAIGN",
        "seal_hash_valid": True,
        "model_fingerprint_match": False,
    }
    r.existing_events = lambda: 1
    r.existing_locks = lambda: 0
    code = r.main(force=False)
    assert code == 3, code
    assert r.SEAL.read_bytes() == before, "seal mutated despite existing observation"
    print("RESEAL_REFUSES_ANY_OBSERVATION=PASS")
finally:
    r.verify_campaign_seal = orig_verify
    r.existing_events = orig_events
    r.existing_locks = orig_locks
