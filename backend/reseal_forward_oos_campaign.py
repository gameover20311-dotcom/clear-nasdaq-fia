#!/usr/bin/env python3
"""Re-seal Forward-OOS only while the current campaign has zero observations.

A campaign seal pins the backend fingerprint so every forward observation is
attributable to one exact production source state. Re-pinning after *any* real
ledger event -- directional forecast, abstention, resolution, or another
production event -- would change that attribution after the fact.

Rules:
1. Archive the previous seal byte-for-byte before any permitted re-seal.
2. Refuse re-seal when ANY ledger event exists. An abstention is a genuine
   forward observation even though it is not a directional forecast lock.
3. If a campaign has observations, close it and start a new campaign instead.
4. BASE_FIA remains production; this script never promotes a model.
5. The seal returns to read-only mode after writing.

The optional --force escape hatch is retained only for recovery tooling and must
never be used to re-attribute a production campaign with observations.
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


def existing_events() -> int:
    """Count every production ledger event, not only forecast-lock files."""
    events = FOOS / "events"
    if not events.is_dir():
        return 0
    return len([p for p in events.glob("*.json") if p.is_file()])


def existing_locks() -> int:
    """Diagnostic subset retained for operator visibility."""
    events = FOOS / "events"
    if not events.is_dir():
        return 0
    return len([p for p in events.glob("*.json") if "forecast-lock" in p.name])


def main(force: bool = False) -> int:
    if not SEAL.exists():
        print("CAMPAIGN_SEAL_MISSING:", SEAL)
        return 2

    before = verify_campaign_seal()
    events = existing_events()
    locks = existing_locks()
    print("current campaign : %s" % before.get("campaign_id"))
    print("ledger events    : %d" % events)
    print("forecast locks   : %d" % locks)
    print("seal_hash_valid  : %s" % before.get("seal_hash_valid"))
    print("fingerprint_match: %s" % before.get("model_fingerprint_match"))

    if before.get("ok"):
        print("\nSeal already valid against the current fingerprint. Nothing to do.")
        return 0

    if events > 0 and not force:
        print("\nREFUSING to re-seal: this campaign already holds %d ledger event(s)." % events)
        print("An abstention is also a genuine forward observation. Re-pinning would")
        print("retroactively change what an existing observation is attributable to.")
        print("Close this campaign and start a new campaign instead.")
        return 3

    old = json.loads(SEAL.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    arch = FOOS / ("SEAL_ARCHIVE_" + stamp)
    arch.mkdir(parents=True, exist_ok=True)
    archived = arch / ("FORWARD_OOS_CAMPAIGN_SEAL_%s.json" % (old.get("campaign_id") or "PREVIOUS"))
    archived.write_bytes(SEAL.read_bytes())
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
    new["supersedes_reason"] = ("backend fingerprint changed while previous campaign held "
                                "%d ledger events and %d forecast locks" % (events, locks))
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
