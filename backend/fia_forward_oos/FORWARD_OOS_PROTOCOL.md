# CLEAR NASDAQ — SOL56 NEW FORWARD OOS PRE-MOVE PROTOCOL

Campaign: `SOL56-NEW-FORWARD-OOS-V4-AUDITED`

## Frozen scientific rules

- Production model: `BASE_FIA`.
- Old historical/observed holdout: **reference only**, `0` untouched rows for future promotion.
- Historical tuning after campaign seal: **forbidden**.
- Live checkpoint: **13:00 America/New_York**, one lock per NY weekday, 10-minute grace.
- Missed checkpoint backfill: **forbidden**.
- Entry/outcome instrument: explicit quarterly NQ contract selected by the live liquidity layer; `NQ=F` continuous fallback is not promotion-eligible.
- Entry and outcome prices: only completed 5-minute bars at/before the requested timestamp.
- Forecast lock: immutable-by-application event + immutable evidence snapshot + SHA256.
- Outcomes: separate append-only `RESOLUTION_4H` and `RESOLUTION_8H` events.
- Event chain: SHA256-linked and anchored by `LEDGER_HEAD.json` so normal tail deletion/editing is detected.
- Filesystem-owner tampering cannot be made cryptographically impossible without an external notarization service; the local design is tamper-evident and fail-closed.
- Minimum interim report: 30 resolved new forecasts.
- Target final sample: 50 resolved new forecasts.
- No automatic BASE replacement.

## Probability semantics

`BASE_FIA` currently produces one pre-move probability distribution. That exact distribution is locked explicitly under both `4h` and `8h` horizon fields and evaluated independently at each outcome horizon. It is labeled `BASE_FIA_SHARED_PREMOVE_DISTRIBUTION`; the system does **not** pretend a separately trained 4H probability exists.

## Promotion rule

Campaign V4 has no shadow candidate sealed, so its promotion verdict is necessarily `NO_PROMOTION`; its purpose is to establish genuine new forward BASE performance.

A future candidate must be sealed **before** its campaign starts and must make paired predictions on the same new timestamps. The candidate is not auto-deployed. Current conservative gate requires at least 50 resolved forecasts on both horizons, candidate Brier improvement of at least 0.005 on both horizons, no accuracy deterioration on either horizon, ECE not worse by more than 0.02, and average accuracy improvement of at least 2 percentage points.

## Metrics

The forward report computes, separately for 4H and 8H:

- resolved sample size
- correct / incorrect
- directional accuracy
- Wilson 95% interval
- Brier score
- ECE and calibration buckets
- confidence-bucket performance
- regime-wise performance
- candidate-vs-BASE promotion gate when a candidate was pre-sealed

No unresolved row is counted as a win or loss, and no losing resolved row is deleted by application code.


## V4 audit reset

V4 starts a new forward-only cohort after the 2026-09-04 deep truth audit. Earlier V1/V2/V3 ledgers are preserved under an archive directory and are never mixed into V4 promotion metrics.
