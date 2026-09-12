# UMSE MASTER — Shadow Research Track

UMSE (FIA Unified Market State Engine) is an isolated research track for CLEAR NASDAQ FIA.

## Status

- Production BASE_FIA: untouched
- Production branch: untouched by this research branch
- UMSE role: SHADOW CANDIDATE ONLY
- Confirmatory campaign: NOT STARTED
- Alpha spent: 0
- Predictive edge: NOT PROVEN

## Scientific question

`I(UMSE_t ; Y_future | FIA_t) > 0 ?`

UMSE only survives if it adds reproducible incremental information beyond BASE_FIA on the same unseen observations.

## Safety boundary

This tree lives under `research/` deliberately. Current production scientific fingerprints cover the backend FIA surface, so Phase 0 work must not silently enter the live model or alter BASE_FIA behaviour.

No UMSE output may feed production forecasts until a later, explicitly reviewed integration phase.

## Phase 0 deliverables

- `spec/UMSE_MASTER_SCIENTIFIC_SPEC_V1.md`
- `spec/umse_master_spec_v1.json`
- typed causal input/output contracts
- latent-state representation
- data-quality and provenance contracts
- fail-closed shadow output
- tests for timestamp, provenance, stale/missing handling and 4H/8H separation

## Validation ladder

1. Scientific specification freeze
2. Causal software scaffold
3. Synthetic/unit verification only
4. Historical replay for debugging/calibration/falsification
5. Untouched historical evaluation where legitimately available
6. Real trial/live feed
7. Locked Forward-OOS
8. Paired BASE vs FIA+UMSE comparison
9. Promote or reject

Historical replay is never prospective proof.
