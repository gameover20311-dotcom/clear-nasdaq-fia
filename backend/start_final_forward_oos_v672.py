#!/usr/bin/env python3
"""Start a NEW Forward-OOS campaign after the first real V5 observation.

This is intentionally NOT a re-seal. Production V5 already recorded one genuine
ABSTENTION_OBSERVATION at 2026-09-08 17:05 UTC under fingerprint 7d95927e...
Changing provider code after that observation requires a new campaign identity.
The old durable row remains under its old campaign_id and is never imported,
rewritten, deleted, or counted in the new campaign.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from fia.forward_oos import canonical_bytes, model_fingerprint, sha256_bytes, verify_campaign_seal

FOOS = BACKEND / "fia_forward_oos"
SEAL = FOOS / "FORWARD_OOS_CAMPAIGN_SEAL.json"
OLD_ID = "CLEAR-NASDAQ-FORWARD-OOS-V5-V662"
NEW_ID = "CLEAR-NASDAQ-FORWARD-OOS-V6-V672"
OLD_FP = "7d95927e6535960939f1ae5bcb1e6f84ffdf712597093e83b578b3374c641209"
OLD_ARCHIVE = FOOS / "SEAL_ARCHIVE_20260908_171806" / (
    "FORWARD_OOS_CAMPAIGN_SEAL_CLEAR-NASDAQ-FORWARD-OOS-V5-V662.json"
)

# Read-only production verification performed immediately before this transition.
# These facts are copied as provenance only; CI does not have database credentials.
OLD_EVENT = {
    "production_rows": 1,
    "directional_rows": 0,
    "abstention_rows": 1,
    "last_seq": 1,
    "event_type": "ABSTENTION_OBSERVATION",
    "event_hash": "aef8f63ab6ecde0ff24b45d191deb0fde3552bf7c7a78559c924ea957dc311de",
    "created_at_utc": "2026-09-08T17:05:03.783241+00:00",
    "model_fingerprint_digest": OLD_FP,
    "durable_store": "Render Postgres",
    "verification": "read-only production query before transition",
}


def main() -> int:
    if not SEAL.exists():
        raise SystemExit("current campaign seal missing")
    if not OLD_ARCHIVE.exists():
        raise SystemExit("byte-for-byte V5 production seal archive missing")

    # The CI checkout contains no production ledger events. Durable V5 history is
    # intentionally left in Postgres under OLD_ID and must never be copied here.
    event_files = sorted((FOOS / "events").glob("*.json")) if (FOOS / "events").is_dir() else []
    if event_files:
        raise SystemExit("refusing new campaign setup: repository event directory is not empty")

    current = json.loads(SEAL.read_text(encoding="utf-8"))
    archived = json.loads(OLD_ARCHIVE.read_text(encoding="utf-8"))
    if str(current.get("campaign_id")) != OLD_ID:
        raise SystemExit("unexpected current campaign id")
    if str(archived.get("campaign_id")) != OLD_ID:
        raise SystemExit("unexpected archived V5 campaign id")
    if str((archived.get("model_fingerprint") or {}).get("digest")) != OLD_FP:
        raise SystemExit("archived V5 fingerprint does not match observed production row")

    fp = model_fingerprint()
    # providers.py/provider_reliability.py are the only production-source changes
    # in this final incident fix; tests/root scripts are outside the fingerprint.
    if not fp.get("digest"):
        raise SystemExit("current model fingerprint unavailable")

    now = datetime.now(timezone.utc)
    new = dict(current)
    new["campaign_id"] = NEW_ID
    new["sealed_at_utc"] = now.isoformat()
    new["model_fingerprint"] = fp
    new["production_model"] = "BASE_FIA"
    new["supersedes_campaign_id"] = OLD_ID
    new["supersedes_reason"] = (
        "V5 recorded one genuine abstention observation before the live-news freshness "
        "provider fix. Because production source changed after that observation, V5 is "
        "closed and V6 starts from N=0; no prior row is imported or backfilled."
    )
    new["previous_seal_archive"] = str(OLD_ARCHIVE.relative_to(BACKEND))
    new["superseded_campaign_observation_summary"] = OLD_EVENT
    new["campaign_start_policy"] = {
        "starts_from_zero": True,
        "import_prior_campaign_rows": False,
        "historical_backfill_allowed": False,
        "missed_checkpoint_backfill_allowed": False,
        "first_eligible_observation": "next normal checkpoint after deployment",
        "old_campaign_remains_preserved_separately": True,
    }
    new.pop("seal_hash", None)
    new["seal_hash"] = sha256_bytes(canonical_bytes(new))

    try:
        os.chmod(SEAL, 0o644)
    except OSError:
        pass
    SEAL.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(SEAL, 0o444)
    except OSError:
        pass

    after = verify_campaign_seal()
    print("NEW_CAMPAIGN_ID=%s" % after.get("campaign_id"))
    print("NEW_MODEL_FINGERPRINT=%s" % fp.get("digest"))
    print("SEAL_HASH_VALID=%s" % after.get("seal_hash_valid"))
    print("FINGERPRINT_MATCH=%s" % after.get("model_fingerprint_match"))
    print("NEW_CAMPAIGN_OK=%s" % after.get("ok"))
    return 0 if after.get("ok") and after.get("campaign_id") == NEW_ID else 1


if __name__ == "__main__":
    raise SystemExit(main())
