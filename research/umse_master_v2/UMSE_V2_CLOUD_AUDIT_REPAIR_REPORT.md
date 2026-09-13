# UMSE MASTER V2 FULL — CLOUD HOSTILE-AUDIT REPAIR REPORT

## Scope

This report records repairs made after the first Cloud AI read-only hostile audit of `research/umse-master-v2-full`.

Production baseline remains:

`1ab93b09d22b77e2bdce99fcfc1418395cbdf78d`

Pre-audit source checkpoint:

`5a8104c314d52c45fed46a8aa647549b0e5403d9`

Repaired source/identity checkpoint:

`fa748fd557abade69445f691e69ac00e1e6d9dba`

Dedicated repaired CI run:

`34698054213`

## Verified repaired CI

- Compile V1 + V2 source: PASS
- Complete V2 suite: **51/51 PASS**
- Identity completeness: PASS
- Production isolation: PASS
- Scientific-status preservation: PASS

## New research identities

- MODEL: `3c77dabaf853d33e04f567ad1fc835b328254141218a72918457157884a24229`
- PROTOCOL: `e62ae32400b3f2d3e2f6d3fb726a11674ca1a985fb44b0a361ff5ba1bfb9bc81`
- INFRASTRUCTURE: `70a93eecf7f36c227f6715e3059a0f12e944fcfba77b7f6236f5cd29e88a3b75`
- Classification manifest: `7de6809074cf39441e7c8cd606e2e6864c0bd0ecb1daf29f5f9852f2190999e4`

The old pre-audit identities are superseded because genuine source repairs changed MODEL, PROTOCOL and package exports. No scientific-identity continuity is claimed.

## Disclosed hostile-audit blockers and repairs

### V2-01 — Time-inconsistent MBO lineage

**Audit failure:** queue reconstruction processed records in sequence order but computed lifetime from event time. A terminal with an earlier event time could be clamped to a zero-second exit and still appear `OBSERVED`.

**Repair:** queue reconstruction now rejects sequence/event-time order conflicts as `PROTOCOL_INELIGIBLE`; negative lifetimes are never converted to zero.

**Regression:** `test_sequence_event_time_conflict_fails_closed`.

### V2-02 — Per-record age filtering creates left truncation

**Audit failure:** an old ADD could be removed by `max_age_seconds` while a recent CANCEL/TRADE remained, selectively deleting long lifetimes.

**Repair:** causal records are collected first, then the age limit defines an observation-window cohort. Lineages known to have entered before the window are excluded as whole left-truncated lineages.

**Regression:** `test_age_window_excludes_entire_left_truncated_lineage`.

### V2-03 — Passive mechanisms mathematically unreachable

**Audit failure:** bid/ask absorption dominated passive accumulation/distribution term-by-term.

**Repair:** passive and absorption hypotheses now use distinct descriptive contexts. Passive accumulation/distribution favours replenishment under lower stress/thinness; absorption favours failed response plus opposing aggression under more stressed conditions. The layer remains heuristic, uncalibrated and non-predictive. Ambiguous/high-entropy competitions do not emit a named leading mechanism.

**Regressions:** passive accumulation and bid absorption are each demonstrably reachable in distinct synthetic contexts.

### V2-04 — Common-driver false directional lead/lag

**Audit failure:** the one-direction circular-shift screen could flag shared burst-clock data as directional lead/lag.

**Repair:** the screen now runs the same null in both directions. A requested source→target screen passes only if forward is significant and reverse is not. Bidirectional significance is labeled `BIDIRECTIONAL_OR_COMMON_DRIVER_PATTERN` and does not pass the directional screen.

**Regression:** a deterministic seeded common-driver burst construction is significant in both raw directional screens but cannot pass the final directional-asymmetry screen.

### V2-05 — Isolation CI could be skipped

**Audit failure:** the V2 workflow used `on.push.paths`; a branch commit touching only production/backend paths would not trigger the isolation test.

**Repair:** path gating was removed. Every push to `research/umse-master-v2-full` now runs the workflow and the explicit diff-based production-isolation check.

**Regression:** workflow text test asserts there is no push `paths:` gate and that the isolation step remains present.

### Inherited V1 alpha propagation defect

**Audit failure:** `ConfirmatoryPlan.alpha` did not control the block-bootstrap confidence level.

**Repair on the V2 branch dependency:** confirmatory bootstrap confidence is now `1 - plan.alpha`, alpha is validated, and `ci_confidence` is recorded in the validation result.

**Regression:** a plan with `alpha=0.01` must report `ci_confidence=0.99`.

### Missing V2 incremental-information screen against FIA

**Audit failure:** V2 did not expose the repaired V1 null-calibrated test for the actual research question `I(UMSE;Y_future|FIA)>0`.

**Repair:** `incremental_value.py` explicitly wraps the conditional-permutation framework. A positive raw CMI is not evidence. A significant result is only `UNCALIBRATED` screening evidence and can never authorize promotion.

**Regressions:** balanced conditional noise does not pass; a deliberately clear conditional signal can pass only as a non-promotional screen.

### Test-strength defects disclosed by mutation attack

The first audit reported that 13/18 destructive mutations survived the original 38-test suite. The repaired suite adds direct tests for the disclosed surviving failure classes, including:

- fixed-N preregistration enforcement
- no early outcome resolution
- Kaplan-Meier survival changes after observed exits
- resistance depletion sign semantics
- mechanism reachability
- chronology and left truncation
- common-driver lead/lag rejection
- alpha propagation
- incremental-information null behavior
- isolation workflow trigger behavior

Current suite: **51/51 PASS**.

This repair report does **not** claim that the exact original 18-mutation battery has been independently reproduced. Cloud AI must rerun its full original mutation battery during re-audit.

## Module integration clarification

The live shadow pipeline intentionally contains the core pre-outcome microstructure path. Other modules are explicit separate research/validation surfaces and are not counted as live-pipeline components merely to increase reachability.

Core live shadow path:

- queue survival / lifetime
- order-book memory
- resistance field
- information velocity
- lead/lag null
- cross-scale transport

Separate surfaces:

- mechanism competition
- counterfactual diagnostics
- topology/regime diagnostics
- model competition
- incremental-information screening
- paired Forward-OOS validation

Outcome-dependent validation must remain outside the pre-outcome shadow path. Whether the separate modules deserve retention is still determined by incremental information on real data, not by code reachability.

## Still deliberately unresolved by code alone

- genuine provider-specific CME/Rithmic/NinjaTrader MBO semantics
- real adapter validation
- real-data calibration
- topology incremental usefulness
- mechanism empirical identifiability
- cross-scale survival into 4H/8H on actual market data
- power-derived confirmatory N
- predictive mapping freeze
- Forward-OOS evidence

These are not converted into synthetic PASS states.

## Preserved status

`SUCCESSOR_CAMPAIGN_STARTED=false`

`ALPHA_SPENT=0`

`PREDICTIVE_EDGE=NOT_PROVEN`

`PRODUCTION_INTEGRATION=false`

`PREDICTIVE_MAPPING_FROZEN=false`

`REAL_MBO_CALIBRATION=NOT_DONE`

`FORWARD_OOS_EDGE=NOT_PROVEN`

## Required next step

Cloud AI must perform a new **read-only hostile re-audit** of the repaired checkpoint and independently re-run all original findings and the full mutation battery. Only accepted closure after that re-audit should proceed to the final independent Astra Max audit.


---

## Correction issued by the final Cloud closeout

This report's mutation claim was wrong and is corrected here rather than edited
away.

`test_isolation_workflow_is_not_path_gated` read the workflow through a
working-directory-relative path. Whenever the suite ran from anywhere but the
repository root it raised `FileNotFoundError`, so the baseline was already red,
every mutated run was also red, and every mutation counted as "detected". The
18/18 reported at checkpoint `fa748fd` was therefore an artefact.

Re-measured from a verified-green baseline, the true score at `fa748fd` was
**11/18**, with these seven scientifically material survivors:

| # | Destroyed behaviour | Class |
|---|---|---|
| 4 | Kaplan-Meier restricted mean survival time forced to zero | MODEL |
| 5 | Order-book half-life forced to a constant | MODEL |
| 6 | Resistance depth term removed | MODEL |
| 9 | Topological persistence entropy replaced | MODEL |
| 10 | Topological fragmentation index forced constant | MODEL |
| 12 | Information-velocity propagation rate forced constant | MODEL |
| 14 | Complexity BIC penalty removed | PROTOCOL |

All seven are killed at the final checkpoint
`c10c6cb0f54af21395702608e0b1e82bce2b19a8`, and the result is reproducible from
three different working directories. The repairs that closed them, plus the six
further defects the closeout found still open, are recorded in
`UMSE_V2_FINAL_CLOUD_CLOSEOUT.md`.
