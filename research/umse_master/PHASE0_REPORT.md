# UMSE MASTER — Phase 0 Report

## Scope

Phase 0 establishes scientific contracts and a fail-closed Shadow-Lab scaffold only. It does not change production FIA behaviour.

## Isolation proof

Branch: `research/umse-master-v1`

Base production commit: `1ab93b09d22b77e2bdce99fcfc1418395cbdf78d`

All Phase-0 changes are under `research/umse_master/`. No production backend file was edited.

## Implemented

- Scientific specification V1
- Machine-readable specification V1
- Data-class taxonomy
- Data-quality taxonomy
- Causal timestamp contract
- Provenance requirements
- Latent-state data contract
- Separate 4H and 8H output contract
- State and mechanism probability contracts
- Probability/confidence separation
- Shadow-only output contract
- Synthetic/proxy exclusion from predictive validation
- Fail-closed `NO_UMSE_EDGE` scaffold
- Production-effect hard rejection in shadow snapshots
- Deterministic provenance hashing

## Contract test result

Exact Phase-0 source was executed in an isolated Python environment:

`9 tests run — 9 PASS`

Covered:

1. future-available data rejected at an earlier decision time
2. synthetic data cannot support predictive validation
3. proxy classification fails closed when proxy flag is inconsistent
4. stale data is ineligible
5. empty input returns `INSUFFICIENT_DATA`
6. real data cannot manufacture edge before a predictive mapping is frozen
7. future-only data returns `PROTOCOL_INELIGIBLE`
8. shadow snapshot cannot set `production_effect=True`
9. provenance hash is deterministic

## Scientific status

This is an architecture/software-contract PASS only.

It does NOT establish:

- predictive edge
- MBO availability
- Hawkes usefulness
- MST usefulness
- state identifiability
- calibration quality
- Forward-OOS improvement

Current status remains:

- `PREDICTIVE_EDGE = NOT_PROVEN`
- `SUCCESSOR_CAMPAIGN_STARTED = false`
- `ALPHA_SPENT = 0`
- `PRODUCTION_INTEGRATION = false`

## Phase-0 verdict

`UMSE_PHASE_0_SPEC_FREEZE_READY = YES`

Reason: causal eligibility, data provenance, proxy/synthetic separation, horizon separation, shadow isolation and kill-switch semantics are now explicit and executable.

The next allowed step is Phase 1: causal event/data kernel and non-predictive market-state primitives. Phase 1 must remain isolated from BASE_FIA.
