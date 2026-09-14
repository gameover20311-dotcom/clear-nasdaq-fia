# SIMONS SHADOW LAB V1 — FINAL READINESS

Date: 2026-09-11

## Verdict

**RESEARCH INFRASTRUCTURE: READY**

This verdict means the isolated research machinery is implemented and its regression/integrity controls pass. It does **not** mean a predictive edge, profitable strategy, or Medallion/Renaissance replication has been proven.

- Predictive edge: **NOT PROVEN**
- Profitability: **NOT PROVEN**
- Automatic production promotion: **DISABLED**
- BASE_FIA modified: **NO**
- Forward-OOS history modified/resealed/backfilled: **NO**

## Isolation evidence

Branch: `research/simons-shadow-lab-v1`

Base main commit: `ebaadf876e5e78ce6ced2b99936aa3eac209d588`

Pre-readiness-file comparison showed 34 commits ahead, 0 behind, with 20 changed files all added, 0 existing production files modified and 0 deleted. This readiness document itself is an additional Shadow-Lab-only file; the final compare must remain add-only before merge consideration.

## CI evidence

GitHub Actions run: `34559906554`

Job: `103140316609`

- Python compile: PASS
- Real test-discovery guard: PASS
- Discovered tests: **22**
- Regression tests: **22/22 PASS**

The suite explicitly covers read-only source behavior, snapshot isolation, anti-leakage, discovery-row exclusion, immutable candidate decisions and later resolutions, hash tamper detection, calibration/robustness/friction reporting, causal lock-time feature isolation, durable-chain tamper detection, experiment registry chaining and hard NOT_PROVEN reporting.

## Real durable Forward-OOS state at readiness check

Read-only Render Postgres query returned:

- `CLEAR-NASDAQ-FORWARD-OOS-V5-V662`: 1 real `ABSTENTION_OBSERVATION`
- `CLEAR-NASDAQ-FORWARD-OOS-V6-V672`: 1 real `FORECAST_LOCK`
- V6 durable `RESOLUTION_4H/8H`: **0**

Therefore genuine candidate performance statistics are not available yet. No candidate edge claim is scientifically allowed at this sample size.

## Implemented research stack

- file-ledger read-only verification
- durable Postgres SELECT-only adapter
- immutable SHA256 snapshots
- hypothesis and experiment registries
- lock-time-only causal feature extraction
- predeclared discovery grids with BH q-values
- regime/state-transition research
- Brier/log-loss/ECE calibration diagnostics
- parameter robustness and signal-decay diagnostics
- immutable standard and causal candidate freezes
- post-freeze-only shadow decision locks
- later separate resolution events
- tamper-evident validation chains
- gross vs explicitly assumed friction reporting
- JSON/Markdown/HTML research reports
- package manifest and final lab-storage audit
- Data Contract, Threat Model and Scientific Protocol
- CLI covering the full research lifecycle

## Scientific rule

The lab may discover hypotheses from completed historical Forward-OOS observations, but a frozen candidate can only be validated by genuinely new forecast locks created after candidate freeze. Discovery rows can never become that candidate's untouched forward validation.

Engineering PASS is not predictive-edge proof.
