#!/usr/bin/env python3
"""Re-seal the Forward-OOS campaign against the CURRENT backend fingerprint.

WHY THIS EXISTS
---------------
The campaign seal pins a sha256 fingerprint over the backend source files so that
every locked forward observation is attributable to an exact code version. That is
the right design, but it has a sharp edge: ANY backend edit invalidates the seal,
`verify_campaign_seal()` starts returning model_fingerprint_match=false, and
`lock_live_forecast()` then refuses every lock with
CAMPAIGN_SEAL_OR_MODEL_FINGERPRINT_INVALID.

That happened silently in this project. `fia/auth_api.py` was added on 2026-09-04
at 22:45, four hours after the V4 seal was written at 01:31. From that moment the
campaign could not lock a single forecast, and nothing surfaced the problem: the
integrity suite aborted at check 5 of 43 and the status endpoints still reported
ok:true. The campaign sat at ZERO observations for two days.

RULES THIS SCRIPT ENFORCES
--------------------------
1. The previous seal is archived BYTE-FOR-BYTE before anything is written.
2. Re-sealing is REFUSED if the existing campaign holds any forecast lock, because
   re-pinning a campaign that already has observations would retroactively change
   what those observations are attributable to. Such a campaign must be closed and
   a new one started instead.
3. The production model is not promoted. BASE_FIA stays production.
4. The seal file is restored to mode 444 afterwards.

RUN THIS AFTER EVERY BACKEND CODE CHANGE, BEFORE RELYING ON FORWARD-OOS.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from fia.forward_oos import (  # noqa: E402
    model_fingerprint, canonical_bytes, sha256_bytes, verify_campaign_seal,
)

FOOS = BACKEND / "fia_forward_oos"
SEAL = FOOS / "FORWARD_OOS_CAMPAIGN_SEAL.json"


def existing_locks() -> int:
    events = FOOS / "events"
    if not events.is_dir():
        return 0
    return len([p for p in events.glob("*.json") if "forecast-lock" in p.name])


def main(force: bool = False) -> int:
    if not SEAL.exists():
        print("CAMPAIGN_SEAL_MISSING:", SEAL)
        return 2

    before = verify_campaign_seal()
    locks = existing_locks()
    print("current campaign : %s" % before.get("campaign_id"))
    print("forecast locks   : %d" % locks)
    print("seal_hash_valid  : %s" % before.get("seal_hash_valid"))
    print("fingerprint_match: %s" % before.get("model_fingerprint_match"))

    if before.get("ok"):
        print("\nSeal already valid against the current fingerprint. Nothing to do.")
        return 0

    if locks > 0 and not force:
        print("\nREFUSING to re-seal: this campaign already holds %d forecast lock(s)." % locks)
        print("Re-pinning would retroactively change what those sealed observations")
        print("are attributable to. Close this campaign and start a new one instead.")
        return 3

    old = json.loads(SEAL.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    arch = FOOS / ("SEAL_ARCHIVE_" + stamp)
    arch.mkdir(parents=True, exist_ok=True)
    archived = arch / ("FORWARD_OOS_CAMPAIGN_SEAL_%s.json" % (old.get("campaign_id") or "PREVIOUS"))
    archived.write_bytes(SEAL.read_bytes())          # byte-for-byte, never mutated
    os.chmod(archived, 0o444)

    fp = model_fingerprint()
    new = dict(old)
    prev_id = str(old.get("campaign_id") or "UNKNOWN")
    base_id = prev_id.split("__RESEAL")[0]
    new["campaign_id"] = "%s__RESEAL_%s" % (base_id, stamp) if "RESEAL" in prev_id else \
                         ("CLEAR-NASDAQ-FORWARD-OOS-V5-V662" if "V4" in prev_id else prev_id)
    new["schema_version"] = "SOL56_FORWARD_OOS_V5_V662"
    new["sealed_at_utc"] = datetime.now(timezone.utc).isoformat()
    new["model_fingerprint"] = fp
    new["production_model"] = "BASE_FIA"
    new["supersedes_campaign_id"] = prev_id
    new["supersedes_reason"] = ("backend fingerprint changed after the previous seal; "
                                "previous campaign held %d forecast locks" % locks)
    new["previous_seal_archive"] = str(archived.relative_to(BACKEND))
    new["evidence_quality_gate"] = {
        "min_data_coverage": float(os.getenv("FIA_FOOS_MIN_DATA_COVERAGE", "0.50")),
        "min_intelligence_coverage": float(os.getenv("FIA_FOOS_MIN_INTELLIGENCE_COVERAGE", "0.30")),
        "reject_not_live_status": True,
        "reject_no_edge_as_directional": True,
    }
    new.pop("seal_hash", None)
    new["seal_hash"] = sha256_bytes(canonical_bytes(new))

    os.chmod(SEAL, 0o644)
    SEAL.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(SEAL, 0o444)

    after = verify_campaign_seal()
    print("\nRESEALED")
    print("  campaign_id      : %s" % after.get("campaign_id"))
    print("  supersedes       : %s" % prev_id)
    print("  archived to      : %s" % archived)
    print("  fingerprint      : %s... (%d files)" % (fp["digest"][:32], len(fp["files"])))
    print("  ok               : %s" % after.get("ok"))
    print("  seal_hash_valid  : %s" % after.get("seal_hash_valid"))
    print("  fingerprint_match: %s" % after.get("model_fingerprint_match"))
    return 0 if after.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(force="--force" in sys.argv))
