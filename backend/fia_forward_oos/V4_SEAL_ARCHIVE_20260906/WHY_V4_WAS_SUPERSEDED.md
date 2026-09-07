# Why the V4 Forward-OOS campaign was superseded (2026-09-06)

The V4 seal is preserved here byte-for-byte and was NOT modified.

## What was wrong
The V4 seal pinned a model fingerprint over 90 backend files,
digest 87df6563badaa300c6f1e3d464cda77f08e3b0ceff296b45b51f53f29160e42e.
`fia/auth_api.py` was added to the backend AFTER the seal was written
(seal 2026-09-04T01:31:47Z; auth feature 2026-09-04T22:45Z), which changed the live
fingerprint to a different digest.

`verify_campaign_seal()` therefore returned model_fingerprint_match=false, and
`lock_live_forecast()` returns CAMPAIGN_SEAL_OR_MODEL_FINGERPRINT_INVALID before
locking anything. **The campaign has been silently unable to lock a single forecast
since 2026-09-04.** That is why the V4 campaign contains 0 forecast locks.

## What was NOT lost
0 event files existed at reseal time and all were left in place.
No sealed forecast was edited, deleted or backdated. The V4 campaign simply never
accumulated any observations.

## What changed in V5
V5 pins the CURRENT V6.6.2 backend fingerprint, which additionally includes the
truth fixes applied in this release (NO_EDGE abstention, honest DERIVED candle
state, evidence-quality gate on lock, freshness discipline). Forward observations
from V5 onward are attributable to that exact code.

Production model remains BASE_FIA. No promotion is implied by this reseal.
