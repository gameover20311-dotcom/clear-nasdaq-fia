# CLOUD AI — UMSE MASTER V2 FULL POST-REPAIR HOSTILE RE-AUDIT

You are performing a **read-only hostile re-audit** of CLEAR NASDAQ FIA — UMSE MASTER V2 FULL after the first hostile audit repair pass.

Do not inherit the repair report as truth. Independently reproduce, attack and falsify the repaired implementation.

## Scope

Repository: `gameover20311-dotcom/clear-nasdaq-fia`

Branch: `research/umse-master-v2-full`

Production base that must remain untouched:

`1ab93b09d22b77e2bdce99fcfc1418395cbdf78d`

Pre-audit source checkpoint:

`5a8104c314d52c45fed46a8aa647549b0e5403d9`

Repaired source/identity checkpoint to audit:

`fa748fd557abade69445f691e69ac00e1e6d9dba`

Dedicated repaired CI run:

`34698054213`

Expected repaired identities — recompute independently rather than trusting them:

- MODEL: `3c77dabaf853d33e04f567ad1fc835b328254141218a72918457157884a24229`
- PROTOCOL: `e62ae32400b3f2d3e2f6d3fb726a11674ca1a985fb44b0a361ff5ba1bfb9bc81`
- INFRASTRUCTURE: `70a93eecf7f36c227f6715e3059a0f12e944fcfba77b7f6236f5cd29e88a3b75`
- Classification manifest: `7de6809074cf39441e7c8cd606e2e6864c0bd0ecb1daf29f5f9852f2190999e4`

Read at minimum:

- `research/umse_master_v2/UMSE_V2_CLOUD_AUDIT_REPAIR_REPORT.md`
- `research/umse_master_v2/UMSE_V2_FINAL_RESEARCH_REPORT.md`
- `research/umse_master_v2/UMSE_V2_BUILD_MANIFEST.json`
- every file under `research/umse_master_v2/src/umse_master_v2/`
- every file under `research/umse_master_v2/tests/`
- `.github/workflows/umse-v2-research.yml`
- repaired V1 dependencies under `research/umse_master/src/umse_master/`, especially `validation.py` and `significance.py`

## FIRST PASS MUST REMAIN READ-ONLY

Do not modify files.
Do not open a PR.
Do not repair anything.
Do not invent missing market data.
Do not reinterpret synthetic tests as predictive evidence.

Return the re-audit report first.

## Mandatory original-finding closure table

Your previous hostile audit contained 17 findings. Re-run **all 17 original findings**, not only the five HIGH findings summarized to the owner.

For every original finding return exactly one state:

- `CLOSED_BY_REPAIR`
- `STILL_OPEN`
- `PARTIALLY_CLOSED`
- `NOT_REPRODUCED`
- `SCIENTIFIC_LIMIT_REMAINS`

For each item show the exact adversarial reproduction command/test or equivalent evidence.

At minimum independently retest these disclosed blockers:

### V2-01 — queue chronology

Attempt to reproduce the former case where sequence order and event time disagree and a terminal precedes its ADD.

The repaired system must never turn a negative lifetime into zero or return clean `OBSERVED` exact survival.

Attack resets, reused sequence ranges, multi-channel normalization and equal timestamps.

### V2-02 — age-window left truncation

Attempt to reproduce an old ADD plus recent terminal event with `max_age_seconds`.

The repair must not preferentially manufacture short lifetimes by dropping the ADD and retaining its terminal event.

Challenge multiple open orders crossing the window boundary and orders added before the window but partially modified inside it.

### V2-03 — unreachable mechanism hypotheses

Re-run the previous random-search/adversarial mechanism distinguishability attack.

Verify passive accumulation/distribution and bid/ask absorption are no longer mathematically dominated.

Then go further: determine whether the repaired distinctions are scientifically identifiable from the stated observables or merely reachable heuristic score regions.

Do not confuse reachability with market identifiability.

### V2-04 — common-driver lead/lag

Re-run the exact previous common-driver attack that produced 60/60 apparent significance.

Verify that the final directional screen now fails when both directions are significant.

Then attack the reverse-direction repair with:

- asymmetric common-driver latency
- autocorrelated bursts
- repeated shocks
- periodic clocks
- duplicated events
- unequal source/target event counts
- feed latency differences
- parameter search across lag windows

A directional screen still does not establish economic causality.

### V2-05 — isolation workflow trigger

Prove that a push touching only `backend/**` on the V2 branch now triggers the V2 workflow and fails the production-isolation diff check.

Do not actually mutate production main.

Challenge symlinks, generated files, workflow changes and path tricks.

### Inherited alpha bug

Verify a plan with `alpha=0.01` produces a 99% bootstrap interval rather than silently using 90%.

Check whether the bootstrap tail indexing and interpretation are internally consistent with that confidence level.

### Incremental-information question

Verify V2 now explicitly exposes the null-calibrated test for:

`I(UMSE_t ; Y_future | FIA_t) > 0`

Attack it with pure noise, conditional confounding, sparse cells, high-cardinality FIA strata, multiple feature searches and repeated experimentation.

A significant screen must remain non-promotional and uncalibrated.

## Mandatory full mutation re-run

Re-run your **complete original 18-mutation battery** against the repaired suite.

Do not accept the existence of 51 tests as evidence of mutation strength.

For each original mutation report:

- mutation description
- whether tests detect it
- exact failing test(s)
- whether the mutation affects MODEL / PROTOCOL / INFRA

The earlier audit found 13/18 survived. Give the new exact detected/18 result. If any scientifically material mutation still survives, classify it as a current TEST_GAP.

At minimum ensure the suite detects destruction of:

- fixed-N enforcement
- outcome-horizon enforcement
- Kaplan-Meier survival update
- resistance depletion sign
- mechanism competition behavior
- queue chronology
- age-window lineage handling
- lead/lag common-driver guard
- plan alpha propagation
- incremental-information null behavior

## Module-reachability / integration audit

The repaired report no longer claims every V2 module is live-pipeline integrated.

Verify the stated architecture split:

**live/pre-outcome shadow core** versus **separate research/validation surfaces**.

Determine whether any separate module is truly dead/unreachable code or whether separation is scientifically appropriate.

Do **not** recommend wiring outcome-dependent validation into the pre-outcome live pipeline merely to improve coverage numbers.

For mechanism competition, topology and counterfactual layers, decide whether they should remain separate, be integrated later after real-data calibration, or be deleted for redundancy.

## Repeat the full hostile audit areas

Independently challenge:

1. production isolation
2. MBO/L2/provider truth
3. causal integrity and future leakage
4. information velocity / lead-lag nulls
5. queue lifetime / censoring
6. order-book memory
7. resistance field
8. latent mechanism competition
9. counterfactual layer
10. topological regime layer
11. cross-scale transport
12. complexity/model competition
13. paired Forward-OOS validation
14. identity/fingerprint integrity
15. test strength
16. mathematical correctness
17. incremental value / redundancy against FIA

## Required classifications

Use exactly:

- `CRITICAL_GENUINE_BUG`
- `HIGH_GENUINE_BUG`
- `MEDIUM_GENUINE_BUG`
- `LOW_GENUINE_BUG`
- `SCIENTIFIC_IDENTIFIABILITY_LIMIT`
- `DATA_READINESS_GAP`
- `TEST_GAP`
- `REDUNDANT_COMPLEXITY`
- `DOCUMENTATION_OR_CLAIM_ISSUE`
- `ALREADY_DEFENDED_CORRECTLY`

For every current defect provide:

1. exact file/function/smallest precise location
2. why it is wrong
3. concrete adversarial example
4. consequence
5. smallest defensible repair
6. required regression test
7. MODEL / PROTOCOL / INFRA identity impact

## Mandatory final verdict table

Return separate verdicts for:

- Engineering correctness
- Production isolation
- Causal integrity
- MBO semantic integrity
- Mathematical correctness
- Statistical-screen integrity
- Mechanism identifiability
- Counterfactual validity
- Topological layer usefulness
- Cross-scale transport validity
- Identity/fingerprint integrity
- Test strength
- Real-data readiness
- Historical diagnostic readiness
- Forward-OOS protocol readiness
- Predictive edge evidence
- Production promotion eligibility

Allowed verdict words:

- `PASS`
- `CONDITIONAL_PASS`
- `FAIL`
- `NOT_TESTED`
- `NOT_ESTABLISHED`
- `NOT_APPLICABLE`

## Non-negotiable scientific status

Do not upgrade these without genuine unseen market evidence:

`SUCCESSOR_CAMPAIGN_STARTED=false`

`ALPHA_SPENT=0`

`PREDICTIVE_EDGE=NOT_PROVEN`

`PRODUCTION_INTEGRATION=false`

`PREDICTIVE_MAPPING_FROZEN=false`

`REAL_MBO_CALIBRATION=NOT_DONE`

`FORWARD_OOS_EDGE=NOT_PROVEN`

Stop after the re-audit report. Do not repair anything until explicitly authorized.
