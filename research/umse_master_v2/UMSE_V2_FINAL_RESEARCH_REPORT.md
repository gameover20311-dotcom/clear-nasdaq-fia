> **SUPERSEDED BY THE FINAL CLOUD CLOSEOUT.**
> The authoritative state of V2 is `UMSE_V2_FINAL_CLOUD_CLOSEOUT.md` at source
> checkpoint `c10c6cb0f54af21395702608e0b1e82bce2b19a8`. Two claims below were
> found wrong by the closeout re-audit and are corrected there: the reported
> 18/18 mutation score at checkpoint `fa748fd` was an artefact of a test that
> failed in every run (the true score was 11/18), and seven scientifically
> material mutations were still surviving at that point. Tests are now 79 and
> the battery is genuinely 18/18 from a verified baseline.

# UMSE MASTER V2 FULL — POST-HOSTILE-AUDIT RESEARCH BUILD REPORT

## Status

**UMSE_V2_ENGINEERING_RESEARCH_BUILD = COMPLETE**

**UMSE_V2_HOSTILE_AUDIT_REPAIR_PASS = COMPLETE_FOR_DISCLOSED_BLOCKERS**

This closes the currently disclosed engineering/scientific-guardrail defects from the first Cloud AI hostile audit. It does **not** claim market edge, production readiness, calibrated forecasting skill, causal identification, real-data readiness, or Forward-OOS proof.

## Repaired source checkpoint

- Branch: `research/umse-master-v2-full`
- Pre-audit source checkpoint: `5a8104c314d52c45fed46a8aa647549b0e5403d9`
- Repaired source/identity checkpoint: `fa748fd557abade69445f691e69ac00e1e6d9dba`
- Dedicated repaired CI run: `34698054213`
- V2 tests: **51/51 PASS**
- Compile: PASS
- Research identity completeness: PASS
- Production isolation from `main`: PASS
- Scientific-status preservation: PASS

V2 research identities at the repaired source checkpoint:

- MODEL: `3c77dabaf853d33e04f567ad1fc835b328254141218a72918457157884a24229` (7 files)
- PROTOCOL: `e62ae32400b3f2d3e2f6d3fb726a11674ca1a985fb44b0a361ff5ba1bfb9bc81` (8 files)
- INFRASTRUCTURE: `70a93eecf7f36c227f6715e3059a0f12e944fcfba77b7f6236f5cd29e88a3b75` (2 files)
- Classification manifest: `7de6809074cf39441e7c8cd606e2e6864c0bd0ecb1daf29f5f9852f2190999e4`

The previous pre-audit identities are superseded because genuine MODEL and PROTOCOL source changed. No continuity claim is made across the repair.

## Hostile-audit repairs now present

1. **Queue chronology fail-closed.** Sequence order that contradicts event-time chronology can no longer produce a zero-second uncensored lifetime. The reconstruction returns protocol-ineligible instead of clamping a negative duration to zero.
2. **Age-window lineage repair.** `max_age_seconds` no longer filters individual records in a way that drops an older ADD while retaining a newer terminal event. Known left-truncated lineages are excluded as a whole.
3. **Mechanism domination removed.** Passive accumulation/distribution and absorption no longer have term-by-term dominated score surfaces. They use distinct descriptive contexts, remain uncalibrated, and ambiguous competitions do not emit a named mechanism.
4. **Common-driver lead/lag guard.** A significant forward circular-shift screen is accepted only when the reverse direction is not also significant. Bidirectional significance is explicitly treated as a common-driver/symmetry warning, not directional evidence.
5. **Isolation CI trigger repaired.** The dedicated V2 verification workflow now runs on every push to the V2 branch rather than only on selected research paths, so a backend-only branch change cannot silently evade the isolation check.
6. **Preregistered alpha wired into the bootstrap.** A confirmatory plan's `alpha` now controls bootstrap confidence as `1-alpha`; a plan declaring 0.01 cannot silently receive a 90% interval.
7. **Incremental-information screen added.** V2 now explicitly exposes the repaired conditional-permutation test for `I(UMSE_t ; Y_future | FIA_t)`. Raw positive plug-in CMI is not evidence; significance is screening-only and never promotion evidence.
8. **Mutation-sensitive regressions added.** Tests now directly protect the disclosed fixed-N, outcome-horizon, Kaplan-Meier, resistance-depletion, chronology, age-window, mechanism-reachability, common-driver, alpha, incremental-information and workflow-isolation failure modes.

## Test-strength boundary

The repaired suite contains 51 passing V2 tests and directly covers the destructive mutations/failures disclosed in the hostile-audit summary. This report does **not** claim that Cloud AI's exact full 18-mutation battery has been independently reproduced. The post-repair re-audit must rerun the original complete hostile battery and report every original finding as CLOSED, OPEN or NOT_REPRODUCED.

## Module-role boundary

The V2 architecture deliberately distinguishes the **live/pre-outcome shadow core** from **separate research/validation surfaces**.

Live/pre-outcome shadow core:

- queue survival
- queue lifetime / hazard
- order-book memory
- resistance field
- information velocity
- lead/lag null screen
- cross-scale transport

Separate research/validation surfaces:

- mechanism competition
- observational counterfactual diagnostics
- topology/regime diagnostics
- complexity/model competition
- incremental-information screening
- paired Forward-OOS validation

These separate surfaces are not silently claimed as live-pipeline integrated. In particular, outcome-dependent validation belongs outside the pre-outcome shadow path. Their incremental usefulness remains an empirical question.

## What V2 contains

1. Genuine-MBO contracts that reject L2/proxy masquerading as order-by-order truth.
2. Queue-survival reconstruction with sequence-domain completeness, lineage, chronology, gap and duplicate safeguards.
3. Censoring-aware Kaplan-Meier queue-lifetime diagnostics.
4. Order-book memory with irregular-sampling refusal rather than false time conversion.
5. Resistance-field diagnostics that refuse requested missing flow inputs.
6. Information-velocity and latency-aware descriptive lead/lag measurements.
7. Bidirectional circular-shift lead/lag screening that remains non-causal and non-promotional.
8. Cross-scale transport gates requiring measured information survival before micro evidence can influence long horizons.
9. Complexity-controlled model competition.
10. Latent mechanism competition that remains heuristic, uncalibrated and non-predictive.
11. Observational counterfactual falsification with overlap and pre-treatment-only boundaries; no self-authorized causal claim.
12. 0D persistent-topology/MST regime diagnostics with causal point eligibility and degenerate-cloud refusal.
13. Explicit conditional incremental-information screening against FIA.
14. V2-specific fixed-N paired Forward-OOS validation with MODEL/PROTOCOL identity matching, horizon timing and preregistration checks.
15. Hierarchical horizon policy: **8H primary confirmatory endpoint; 4H separate secondary endpoint.**
16. Separate self-inclusive MODEL / PROTOCOL / INFRA research fingerprints.
17. Dedicated CI proving compilation, tests, identity completeness, production isolation and preserved scientific status.

## Hard scientific boundaries

The following remain unchanged:

- `SUCCESSOR_CAMPAIGN_STARTED=false`
- `ALPHA_SPENT=0`
- `PREDICTIVE_EDGE=NOT_PROVEN`
- `PRODUCTION_INTEGRATION=false`
- `PREDICTIVE_MAPPING_FROZEN=false`
- `REAL_MBO_CALIBRATION=NOT_DONE`
- `FORWARD_OOS_EDGE=NOT_PROVEN`

A green engineering suite is not evidence that UMSE improves NQ forecasts. Synthetic tests prove software contracts and failure behavior only.

## What cannot honestly be completed in code alone

The next scientific steps still require external evidence:

1. Legitimate NQ MBO/depth/trades with verified provider semantics, licensing and availability timestamps.
2. Real adapter semantic verification; no L2-to-MBO promotion.
3. Causal historical debug/calibration only.
4. Freeze a candidate mapping after calibration.
5. Untouched historical evaluation.
6. Zero-alpha forward pilot to estimate dependence/variance and derive confirmatory N.
7. Preregistered fixed-N Forward-OOS BASE vs FIA+UMSE evaluation, 8H primary and 4H secondary.
8. Promotion only after the frozen gate and independent audits pass.

## Current engineering verdict

The disclosed first-pass hostile-audit blockers have been repaired and the repaired checkpoint is ready for a **read-only Cloud AI re-audit**. That re-audit must independently rerun the original 17-finding audit, including the full mutation battery, rather than accepting this report as proof.

The project is **not** ready to be called a proven predictive system.
